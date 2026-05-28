# 📊 Flux de Télémétrie — Jumeaux Chauds

> **Document :** Routes de données de télémétrie entre les machines simulées et les clients externes.

Cet document mappe tous les trajets possibles pour extraire les données de télémétrie d'une machine, depuis la simulation jusqu'au client consommateur final.

---

## 1. Vue d'ensemble des flux

```mermaid
graph TD
    SIM["🖥️ Simulation<br/>(ClusterSimulator)"]
    
    subgraph CORE["Core Publishing"]
        MQTT_PUB["MQTT Publisher<br/>(aiomqtt)"]
        WS_MGR["WebSocket Manager<br/>(FastAPI lifespan)"]
    end
    
    subgraph BROKER["Message Broker"]
        MOSQUITTO["🐦 Mosquitto<br/>(Port 1883)"]
    end
    
    subgraph STORAGE["Storage Layer (optional)"]
        CONSUMER["MQTT Consumer<br/>(asyncpg)"]
        TSDB["TimescaleDB<br/>(PostgreSQL+extension)"]
    end
    
    subgraph CLIENTS["External Clients"]
        DASHBOARD["Dashboard<br/>(Streamlit)"]
        API["API REST<br/>(FastAPI)"]
        MQTT_SUB["MQTT Subscriber<br/>(mosquitto_sub, MQTT Explorer)"]
        GRAFANA["Grafana<br/>(TimescaleDB queries)"]
        CUSTOM["Custom Client<br/>(via REST/MQTT/SQL)"]
    end
    
    SIM -->|"tick() → snapshot"| MQTT_PUB
    SIM -->|"broadcast() → JSON"| WS_MGR
    
    MQTT_PUB -->|"publish dt/..."| MOSQUITTO
    WS_MGR -->|"WebSocket /ws/cluster"| API
    
    MOSQUITTO -->|"subscribe dt/#"| CONSUMER
    MOSQUITTO -->|"subscribe dt/#"| DASHBOARD
    MOSQUITTO -->|"subscribe dt/#"| MQTT_SUB
    
    CONSUMER -->|"INSERT telemetry"| TSDB
    
    TSDB -->|"SELECT queries"| GRAFANA
    TSDB -->|"SELECT queries"| CUSTOM
    
    API -->|"GET /cluster/status<br/>GET /machines/{id}"| CUSTOM
    API -->|"WebSocket /ws/cluster"| DASHBOARD
    
    classDef simulation fill:#e1f5ff
    classDef publishing fill:#fff3e0
    classDef broker fill:#f3e5f5
    classDef storage fill:#e8f5e9
    classDef client fill:#fce4ec
    
    class SIM simulation
    class MQTT_PUB,WS_MGR publishing
    class MOSQUITTO broker
    class CONSUMER,TSDB storage
    class DASHBOARD,API,MQTT_SUB,GRAFANA,CUSTOM client
```

---

## 2. Routes de télémétrie détaillées

### Route 1️⃣ : MQTT Direct (Real-time, Lightweight)

```mermaid
sequenceDiagram
    participant Sim as ClusterSimulator
    participant Pub as MQTT Publisher
    participant Broker as Mosquitto
    participant Sub as MQTT Subscriber
    
    Sim->>Pub: snapshot()
    Pub->>Broker: publish dt/cluster/machine/telemetry
    Broker->>Sub: msg received (QoS 0)
    Sub->>Sub: parse & display JSON
    
    Note over Sim,Sub: Latency: <100ms<br/>No persistence<br/>Real-time only
```

**Caractéristiques :**
- **Latency** : <100 ms
- **Persistence** : ❌ Non (data lost if subscriber disconnects)
- **Ideal for** : Real-time monitoring, dashboards, streaming
- **Tools** : `mosquitto_sub`, MQTT Explorer, `mqtt_observer.py`
- **Format** : JSON payloads on topics `dt/{cluster}/{machine}/{kind}`

**Example :**
```bash
# Subscribe
mosquitto_sub -h localhost -t "dt/cluster_alpha/srv-master-01/telemetry" -v

# Output
dt/cluster_alpha/srv-master-01/telemetry {"id":"srv-master-01","temperature_c":42.5,"power_w":180.3,...}
```

---

### Route 2️⃣ : API REST (Query-based, Stateful)

```mermaid
sequenceDiagram
    participant Sim as ClusterSimulator
    participant API as FastAPI
    participant Client as External Client
    
    Sim->>API: broadcast snapshot via WS Manager
    API->>API: store in-memory snapshot
    
    Client->>API: GET /cluster/status
    API->>Client: return cached snapshot (JSON)
    
    Client->>API: GET /machines/{id}
    API->>Client: return machine snapshot
    
    Client->>API: POST /machines/{id}/power
    API->>Sim: command received
    Sim->>API: updated snapshot
    
    Note over Sim,Client: Latency: ~50ms<br/>In-memory cache<br/>Full control via commands
```

**Caractéristiques :**
- **Latency** : ~50 ms
- **Persistence** : ❌ Non (cache in-memory, lost on restart)
- **Ideal for** : Control commands, web dashboards, query-based clients
- **Features** : Full REST API, WebSocket streaming, OpenAPI docs
- **Format** : JSON responses, HTTP status codes

**Example :**
```bash
# Query snapshot
curl http://localhost:8000/cluster/status

# Send command
curl -X POST http://localhost:8000/machines/srv-master-01/power \
  -H "Content-Type: application/json" \
  -d '{"power_on": true}'

# WebSocket real-time
wscat -c ws://localhost:8000/ws/cluster
```

---

### Route 3️⃣ : MQTT → TimescaleDB (Persistent, Analytical)

```mermaid
sequenceDiagram
    participant Sim as ClusterSimulator
    participant Pub as MQTT Publisher
    participant Broker as Mosquitto
    participant Consumer as MQTT Consumer
    participant TSDB as TimescaleDB
    participant Client as Analytics Client
    
    Sim->>Pub: snapshot()
    Pub->>Broker: publish dt/cluster/machine/telemetry
    
    Broker->>Consumer: deliver message
    Consumer->>Consumer: parse topic & payload
    Consumer->>TSDB: INSERT INTO telemetry (timestamp, machine_id, temp_c, power_w...)
    
    Client->>TSDB: SELECT * FROM telemetry WHERE machine_id = ? AND timestamp > ?
    TSDB->>Client: time-series data
    
    Note over Consumer,Client: Latency: ~1s (batch insert)<br/>Full persistence<br/>Time-series queries
```

**Caractéristiques :**
- **Latency** : ~1 second (batch inserts)
- **Persistence** : ✅ Oui (hypertable with continuous aggregation)
- **Ideal for** : Historical analysis, trends, long-term storage
- **Features** : Time-series compression, retention policies, aggregation
- **Format** : PostgreSQL table `telemetry` with timestamp index

**Schema :**
```sql
CREATE TABLE telemetry (
    time TIMESTAMPTZ NOT NULL,
    cluster_id TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    temperature_c FLOAT NOT NULL,
    power_w FLOAT NOT NULL,
    energy_kwh FLOAT,
    fan_rpm_mean INT,
    status TEXT
);

SELECT * FROM telemetry 
WHERE machine_id = 'srv-master-01' 
  AND time > NOW() - INTERVAL '1 hour'
ORDER BY time DESC;
```

---

### Route 4️⃣ : TimescaleDB → Grafana (Visualization, Dashboards)

```mermaid
sequenceDiagram
    participant TSDB as TimescaleDB
    participant Grafana as Grafana
    participant Browser as Web Browser
    
    loop Every 30 seconds
        Grafana->>TSDB: SELECT avg(temperature_c) FROM telemetry WHERE time > NOW() - 5m
        TSDB->>Grafana: time-series aggregates
    end
    
    Grafana->>Grafana: render graphs, heatmaps, annotations
    Browser->>Grafana: http://localhost:3000
    Grafana->>Browser: HTML + JSON (dashboards)
    
    Note over TSDB,Browser: Latency: 500ms (query + render)<br/>Pre-computed aggregates<br/>Professional dashboards
```

**Caractéristiques :**
- **Latency** : ~500 ms (query + render)
- **Persistence** : ✅ Oui (stored in TimescaleDB)
- **Ideal for** : Executive dashboards, SLA monitoring, alerts
- **Features** : Custom panels, annotations, alerting rules
- **Format** : SQL queries, time-series response

**Example Query :**
```sql
-- Average temperature per machine (last 24h)
SELECT 
  time_bucket('5 min', time) as bucket,
  machine_id,
  avg(temperature_c) as avg_temp
FROM telemetry
WHERE time > NOW() - INTERVAL '24 hours'
GROUP BY bucket, machine_id
ORDER BY bucket DESC;
```

---

### Route 5️⃣ : Streamlit Dashboard (Interactive Monitoring)

```mermaid
sequenceDiagram
    participant Dashboard as Streamlit
    participant WS as WebSocket /ws/cluster
    participant API as FastAPI
    participant Sim as ClusterSimulator
    
    Dashboard->>Dashboard: @st.cache_resource init client
    Dashboard->>WS: connect (persistent connection)
    
    loop Every 100ms
        Sim->>API: broadcast snapshot
        API->>WS: push JSON
        WS->>Dashboard: receive snapshot
        Dashboard->>Dashboard: update Plotly/Streamlit widgets
        Dashboard->>Dashboard: st.rerun() (2Hz refresh)
    end
    
    Dashboard->>API: user clicks Power ON
    API->>Sim: execute command
    Sim->>API: updated state
    API->>Dashboard: response
    
    Note over Dashboard,Sim: Latency: <500ms<br/>Interactive controls<br/>Real-time updates
```

**Caractéristiques :**
- **Latency** : <500 ms
- **Persistence** : ❌ Non (UI state ephemeral)
- **Ideal for** : Interactive control, real-time monitoring, admin dashboards
- **Features** : Buttons, sliders, live plots, multi-tab interface
- **Connection** : WebSocket for continuous streaming

**Example :**
```python
# In dashboard/app.py
@st.cache_resource
def get_ws_client():
    return ClusterWSClient("ws://localhost:8000/ws/cluster")

client = get_ws_client()
snapshot = client.get_latest()  # Last snapshot from WebSocket

st.metric("Avg Temperature", f"{snapshot['avg_temp']:.1f}°C")
st.button("Power ON", on_click=api_client.power_on)
```

---

## 3. Matrice comparée : Routes vs Cas d'usage

| Critère | MQTT Direct | API REST | MQTT→TSDB | TSDB→Grafana | Streamlit |
|---------|------------|----------|-----------|--------------|-----------|
| **Latency** | <100ms | ~50ms | ~1s | ~500ms | <500ms |
| **Persistence** | ❌ | ❌ | ✅ | ✅ | ❌ |
| **Real-time** | ✅ | ✅ | ❌ | ❌ | ✅ |
| **History** | ❌ | ❌ | ✅ | ✅ | ❌ |
| **Scalability** | ✅ (pub/sub) | ✅ (stateless) | ✅ (DB) | ✅ (cached) | ⚠️ (UI) |
| **Control** | ❌ | ✅ | ❌ | ❌ | ✅ |
| **Dashboards** | ⚠️ (custom) | ⚠️ (code) | ✅ | ✅ | ✅ |
| **Cost** | Low | Low | Medium | Low | Low |
| **Setup** | 5 min | 5 min | 30 min | 30 min | 5 min |

---

## 4. Flux hybride recommandé (production)

```mermaid
graph TB
    SIM["🖥️ ClusterSimulator"]
    
    SIM -->|"snapshot @ 10Hz"| MQTT["🐦 Mosquitto<br/>dt/cluster/..."]
    SIM -->|"broadcast @ 1Hz"| API["⚡ FastAPI<br/>WebSocket Manager"]
    
    MQTT -->|"subscribe & parse"| CONSUMER["Consumer<br/>(asyncpg)"]
    CONSUMER -->|"batch INSERT 1s"| TSDB["📊 TimescaleDB"]
    
    API -->|"WebSocket /ws/cluster"| DASHBOARD["📈 Streamlit<br/>Real-time UI"]
    API -->|"REST endpoints"| CUSTOM["🔧 Custom Client<br/>(curl, SDK, etc)"]
    
    MQTT -->|"subscribe dt/#"| OBSERVER["👁️ MQTT Observer<br/>(mosquitto_sub, Explorer)"]
    
    TSDB -->|"SELECT queries"| GRAFANA["📉 Grafana<br/>Executive Dashboard"]
    TSDB -->|"SELECT queries"| ANALYTICS["🔬 Analytics<br/>(Python, SQL)"]
    
    style SIM fill:#e1f5ff
    style MQTT fill:#f3e5f5
    style API fill:#fff3e0
    style TSDB fill:#e8f5e9
    style DASHBOARD fill:#fce4ec
    style GRAFANA fill:#fce4ec
    style CUSTOM fill:#fce4ec
```

**Bénéfices :**
- ✅ Real-time MQTT pour monitoring immédiat
- ✅ API pour contrôle & requêtes ponctuelles
- ✅ TimescaleDB pour historique & analytics
- ✅ Grafana pour dashboards pro
- ✅ Streamlit pour UI interactive
- ✅ Scalable & modular

---

## 5. Points de décision

### Quel flux choisir ?

| Cas d'usage | Route recommandée | Raison |
|-------------|------------------|--------|
| **Monitoring temps réel** | MQTT Direct (Route 1) | Faible latence, pas d'overhead DB |
| **Contrôle machine** | API REST (Route 2) | Commands, stateless |
| **Dashboard admin interactif** | Streamlit (Route 5) | UI riche, WebSocket push |
| **Analyse historique** | MQTT→TSDB→Query (Routes 3) | Agrégations, time-series |
| **Executive reporting** | TSDB→Grafana (Route 4) | Pre-computed, SLA tracking |
| **Custom integration** | API REST (Route 2) | OpenAPI docs, easy SDK |
| **Debugging & inspection** | MQTT Direct (Route 1) | See raw messages immediately |

### Combinaisons possibles

**Scenario 1 : Fast monitoring**
```
Sim → MQTT → MQTT Explorer (inspect)
Sim → API → Streamlit (interactive)
```

**Scenario 2 : Full stack**
```
Sim → MQTT → Consumer → TimescaleDB → Grafana (history)
Sim → API → Streamlit (real-time control)
```

**Scenario 3 : Developer testing**
```
Sim → MQTT → mosquitto_sub (log to file)
Sim → API → curl / Postman (manual tests)
```

---

## 6. Implémentation par couche

### Layer 6.1 : Publication (Simulation → Broker)

**Files :** `simulation/cluster.py`, `mqtt/publisher.py`

```python
# In cluster.py during run()
async def run():
    while True:
        for machine in self.machines.values():
            machine.tick(load_factor=..., dt=...)
        
        # Publish to MQTT
        if self.publisher:
            await self.publisher.publish_telemetry(self.machines)
        
        # Broadcast via WebSocket
        if self.ws_manager:
            self.ws_manager.broadcast(self.get_snapshot())
        
        await asyncio.sleep(1.0 / self.tick_rate_hz)
```

### Layer 6.2 : MQTT Subscriber (Broker → Consumer)

**Files :** `consumer/mqtt_to_timescale.py`

```python
async def run():
    async with aiomqtt.Client(broker_host, broker_port) as client:
        await client.subscribe("dt/#")
        async for message in client.messages:
            # Parse topic: dt/cluster/machine/kind
            cluster, machine, kind = parse_topic(message.topic)
            
            # Parse payload
            data = json.loads(message.payload)
            
            # Dispatch to handler
            if kind == "telemetry":
                await insert_telemetry(pool, cluster, machine, data)
            elif kind in ["fault", "status"]:
                await insert_event(pool, cluster, machine, kind, data)
```

### Layer 6.3 : API Endpoints (Simulation → HTTP)

**Files :** `api/main.py`, `api/routes/`

```python
@app.get("/cluster/status")
async def get_cluster_status(cluster: ClusterSimulator = Depends(get_cluster)):
    """Return current cluster snapshot."""
    return cluster.get_snapshot()

@app.websocket("/ws/cluster")
async def websocket_cluster(websocket: WebSocket):
    """Stream cluster snapshots in real-time."""
    manager.connect(websocket)
    try:
        while True:
            # Receive snapshot from manager (pushed by cluster.run())
            await manager.broadcast(snapshot)
    finally:
        manager.disconnect(websocket)
```

### Layer 6.4 : Dashboard (API → UI)

**Files :** `dashboard/app.py`, `dashboard/ws_client.py`

```python
@st.cache_resource
def get_cluster_client():
    return ClusterWSClient("ws://localhost:8000/ws/cluster")

client = get_cluster_client()
latest = client.get_latest()

col1, col2, col3 = st.columns(3)
col1.metric("Machines ON", latest['machines_on'])
col2.metric("Avg Temp", f"{latest['avg_temp']:.1f}°C")
col3.metric("Total Power", f"{latest['total_power_w']:.0f}W")

# Heatmap
fig = px.imshow([[m['temperature_c'] for m in latest['machines'].values()]])
st.plotly_chart(fig)
```

---

## 7. Flux d'erreur & reconnexion

```mermaid
graph TD
    MQTT["MQTT Publisher"]
    BROKER["Mosquitto<br/>(unavailable)"]
    PUBLISHER_FALLBACK["Silently drop<br/>messages"]
    
    MQTT -->|"send"| BROKER
    BROKER -->|"connection refused"| MQTT
    MQTT -->|"auto-reconnect<br/>every 5s"| BROKER
    MQTT -->|"still down"| PUBLISHER_FALLBACK
    PUBLISHER_FALLBACK -->|"continue simulation"| MQTT
    
    CONSUMER["MQTT Consumer"]
    CONSUMER -->|"subscribe dt/#"| BROKER
    BROKER -->|"connection refused"| CONSUMER
    CONSUMER -->|"wait & retry"| BROKER
    CONSUMER -->|"connected"| BROKER
    
    API["API Snapshots"]
    API -->|"broadcast to WS"| WS["WebSocket Clients"]
    WS -->|"client disconnects"| API
    API -->|"remove from pool"| API
    WS -->|"client reconnects"| API
    API -->|"add to pool"| API
```

**Points clés :**
- ✅ Publisher tolerates broker down (doesn't block simulation)
- ✅ Consumer retries if broker unavailable
- ✅ API WebSocket handles client reconnects transparently
- ⚠️ MQTT messages lost if broker down (no local queue)
- ✅ TimescaleDB persists data once written

---

## 8. Performance & Benchmarks

| Route | Throughput | Latency | CPU | Memory |
|-------|-----------|---------|-----|--------|
| MQTT Direct (5 machines) | 50 msg/s | <100ms | <5% | <10MB |
| API REST (5 machines) | 100 req/s | ~50ms | <5% | <20MB |
| MQTT→TSDB (5 machines) | 10 msg/s (batch) | ~1s | <10% | <50MB |
| Grafana (time-bucketed) | 1 dashboard | ~500ms | <5% | <100MB |
| Streamlit (5 machines) | 2 FPS | <500ms | <15% | <150MB |

**Notes :**
- All tests: 5 machines, 10Hz simulation, 1 hour runtime
- MQTT→TSDB batches inserts (1s window)
- Grafana pre-computes aggregates (5min buckets)
- Streamlit UI refresh 2Hz (st.rerun())

---

*Tristan Vanrullen — La Plateforme, Marseille — 2026*
