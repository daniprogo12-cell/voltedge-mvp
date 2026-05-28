# VoltEdge ML Analysis Project

Dette er en tilpasset version af det lille VoltEdge machine learning-projekt til dataanalyse-afsnittet i rapporten.

Projektet bruger nu både:

1. `data/simulated_yearly_charger_data.csv` som demonstrativ 1-årig historisk træningsdata.
2. De aktuelle MVP-store JSON-filer:
   - `data/telemetry_store.json`
   - `data/health_store.json`
   - `data/maintenance_store.json`

De tre JSON-filer samles i koden til ét samlet in-memory store med disse collections:

- `telemetry_readings`
- `health_snapshots`
- `anomalies`
- `maintenance_recommendations`
- `incidents`

## Hvorfor både CSV og JSON?

De uploadede JSON-filer indeholder kun et meget lille aktuelt snapshot. Det er derfor ikke nok data til at træne en statistisk meningsfuld ML-model alene.

Derfor gør projektet to ting:

1. Træner en simpel lineær regressionsmodel på den syntetiske historiske CSV.
2. Omsætter de aktuelle JSON-data til de samme features og scorer de aktuelle ladestandere.

Derudover beregnes en transparent `operational_risk_score` fra 0-100, som er bedre egnet til at prioritere det aktuelle snapshot, fordi JSON-dataene allerede indeholder direkte faresignaler som lav health score, offline status, manglende heartbeat, anomalies og incidents.

## Model

- Modeltype: simpel lineær regression med NumPy least squares.
- Target: `incident_count_next_30_days`.
- Features:
  - `avg_health_score`
  - `error_count`
  - `offline_events`
  - `missing_heartbeat_count`
  - `avg_power_kw`
  - `anomaly_count`
  - `previous_incidents`

## Aktuel risikoprioritering fra JSON

Outputfilen `outputs/current_store_risk_predictions.csv` indeholder bl.a.:

- `predicted_incidents_next_30_days`
- `ml_risk_category`
- `operational_risk_score`
- `operational_risk_category`

`operational_risk_score` bruges til den aktuelle maintenance-prioritering, fordi den direkte afspejler de uploadede JSON-signaler.

## Output

Projektet genererer:

1. `outputs/predictions_test_period.csv`  
   Historiske testprediktioner fra demo-modellen.

2. `outputs/current_store_risk_predictions.csv`  
   Aktuel risikoprioritering baseret på de tre JSON-store filer.

3. `outputs/merged_current_store.json`  
   Den samlede version af de tre JSON-store filer.

4. `outputs/diagram_1_actual_vs_predicted.png`  
   Valideringsdiagram for historisk testdata.

5. `outputs/diagram_2_current_store_risk_ranking.png`  
   Prioritering af aktuelle ladestandere ud fra JSON-data.

6. `outputs/model_summary.json`  
   Modelmetadata, featureliste, metrikker og top-risiko-ladestander.

## Sådan køres projektet

```bash
pip install -r requirements.txt
python src/train_predictive_maintenance.py
```

## Resultat med de aktuelle JSON-data

Med de medfølgende JSON-filer prioriteres ladestanderne sådan:

1. `CH-004` - høj operationel risiko
2. `CH-003` - medium operationel risiko
3. `CH-001` - lav operationel risiko
4. `CH-002` - lav operationel risiko

## Vigtig afgrænsning

Resultaterne er demonstrative. Modellen er stadig trænet på syntetiske historiske data, mens de aktuelle JSON-filer bruges som et driftssnapshot. I en rigtig løsning bør modellen trænes på faktiske historiske telemetry-, health-, anomaly- og incident-data over en længere periode.
