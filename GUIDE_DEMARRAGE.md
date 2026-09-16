# AuroRatio — Guide de Démarrage
### De l'installation au bot en production

---

## Prérequis

Avant de commencer, assurez-vous d'avoir :

- **Python 3.10+** installé
- **Node.js 18+** installé (pour le frontend)
- **IB Gateway** installé et configuré (compte paper trading actif)
- Une connexion internet active

---

## PARTIE 1 — Bot de Trading (Phase 1)

---

## 1. Installation des dépendances bot

À faire une seule fois depuis la racine du projet.

```bash
pip install yfinance==0.2.61 pandas matplotlib pyyaml schedule ib_insync python-dotenv passlib[bcrypt] bcrypt==4.3.0
```

> **Pourquoi yfinance 0.2.61 ?**
> Les versions plus récentes ont un conflit avec les drivers SQLite.
> La version 0.2.61 est stable et validée pour ce projet.

---

## 2. Configurer les secrets

Créer un fichier `.env` à la racine :

```
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
JWT_SECRET_KEY=votre_clé_secrète_générée
```

Générer la clé JWT :
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

> **Ne jamais committer `.env` sur GitHub.**

---

## 3. Vérifier la configuration

Ouvrir `config.yaml` et vérifier :

```yaml
broker:
  host: "127.0.0.1"
  port: 4002          # 4002 = paper trading | 4001 = compte réel
  client_id: 1

backtest:
  start_date: "2000-01-01"
  end_date:   "2025-12-31"
  initial_capital: 100000
  transaction_cost_percent: 0.20

security_limits:
  trade_delay_days: 2
  fee_reserve_percent: 0.5

ratios:
  silver:    { buy: 80.0,  sell: 40.0  }
  platinum:  { buy: 2.0,   sell: 0.45  }
  palladium: { buy: 4.0,   sell: 0.9   }
```

Ne rien modifier ici sauf le port si vous passez en compte réel.

---

## 4. Télécharger les données historiques

### Mode live (jusqu'à aujourd'hui) — recommandé pour la production :
```bash
python download_data.py
```

### Mode backtest (jusqu'au 31/12/2025) — pour reproduire les résultats du rapport :
```bash
python download_data.py --backtest
```

### Mode repair (combler les gaps) :
```bash
python download_data.py --repair
```

**Ce que ça produit :**
```
data/prices_raw.csv    ← données brutes avec les gaps
data/prices_clean.csv  ← données forward-fillées, utilisées par le backtest
```

**Durée estimée :** 30–60 secondes (5 téléchargements avec délai entre chaque).

> **Note :** Les données Yahoo Finance sont disponibles à partir du 30/08/2000.
> Le backtest démarrera donc à cette date malgré la config `start_date: 2000-01-01`.

---

## 5. Vérifier les ratios

Optionnel mais recommandé.

```bash
python ratios.py
```

---

## 6. Lancer le backtest

### Version 3 modules (recommandée) :
```bash
python backtest.py
```

### Version 1 module (résultats du rapport d'audit) :
Modifier la dernière ligne de `backtest.py` pour appeler `run_backtest_1module()`.

---

## 7. Générer les graphiques

```bash
python charts.py
```

---

## 8. Tester la connexion IB Gateway

**IB Gateway doit être ouvert.**

```bash
python broker.py
```

---

## 9. Lancer le cycle quotidien manuellement (test)

**IB Gateway doit être ouvert.**

```bash
python scheduler.py --now
```

---

## 10. Lire le rapport quotidien

```bash
python report.py
```

---

## 11. Démarrer le scheduler en mode production

**IB Gateway doit être ouvert en permanence.**
Configurer IB Gateway en "Auto Restart" :
`Configure → Settings → Lock and Exit → Auto Restart`

```bash
python scheduler.py
```

---

## PARTIE 2 — Plateforme Web (Phase 2)

---

## 12. Installation backend

```bash
cd backend
pip install fastapi uvicorn[standard] sqlalchemy alembic psycopg2-binary \
  python-dotenv python-jose[cryptography] passlib[bcrypt] bcrypt==4.3.0 \
  httpx stripe snaptrade-python-sdk slowapi pydantic[email]
```

Ajouter au `.env` (à la racine, partagé entre bot et backend) :
```
DATABASE_URL=sqlite:///./auroratio.db
JWT_SECRET_KEY=votre_clé_secrète
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...
SNAPTRADE_CLIENT_ID=...
SNAPTRADE_CONSUMER_KEY=...
SUBSCRIPTION_PRICE=49
SUBSCRIPTION_CURRENCY=EUR
```

---

## 13. Démarrer le backend

```bash
cd backend
uvicorn main:app --reload
```

API disponible sur `http://localhost:8000`
Documentation Swagger : `http://localhost:8000/docs`

---

## 14. Installation frontend

```bash
cd frontend
npm install
```

Créer `frontend/.env` :
```
VITE_API_URL=http://localhost:8000
```

---

## 15. Démarrer le frontend

```bash
cd frontend
npm run dev
```

Application disponible sur `http://localhost:5173`

---

## 16. Premier lancement complet (local)

Dans trois terminaux séparés :

```bash
# Terminal 1 — Backend
cd backend && uvicorn main:app --reload

# Terminal 2 — Frontend
cd frontend && npm run dev

# Terminal 3 — Bot scheduler (optionnel, pour tester le cycle)
python scheduler.py
```

---

## PARTIE 3 — Déploiement Azure

---

## 17. Séquence de déploiement

```
1. Créer VM Azure (App Service B2 ou VM Ubuntu)
2. Cloner le repo GitHub sur le serveur
3. Configurer .env sur le serveur (jamais dans le repo)
4. pip install -r requirements.txt (bot) + backend/requirements.txt
5. python download_data.py          ← UNE SEULE FOIS au déploiement
6. Configurer systemd pour le backend (uvicorn)
7. Configurer systemd pour le scheduler (python scheduler.py)
8. Configurer Nginx (reverse proxy vers port 8000)
9. Obtenir certificat SSL via certbot
10. npm run build dans frontend/ → copier dist/ dans Nginx
11. Tester : signup → subscribe → dashboard
12. Passer port 4002 → 4001 dans config.yaml (compte réel)
```

> **Note déploiement :** `download_data.py` n'est exécuté qu'une seule fois
> le jour du déploiement. Après cela, le scheduler ajoute une ligne par jour
> automatiquement via `fetch_latest_prices()`.

---

## Fichiers produits — récapitulatif

| Fichier | Produit par | Description |
|---|---|---|
| `data/prices_raw.csv` | `download_data.py` | Prix bruts Yahoo Finance |
| `data/prices_clean.csv` | `download_data.py` | Prix forward-fillés |
| `data/backtest_module1_silver.csv` | `backtest.py` | Résultats module Or/Argent |
| `data/backtest_module2_platinum.csv` | `backtest.py` | Résultats module Or/Platine |
| `data/backtest_module3_palladium.csv` | `backtest.py` | Résultats module Or/Palladium |
| `data/backtest_1module_phase1.csv` | `backtest.py` | Résultats Phase 1 — référence rapport |
| `data/chart1_wealth_curve.png` | `charts.py` | Courbe de richesse |
| `data/chart2_ounce_accumulation.png` | `charts.py` | Effet escalier |
| `data/chart3_currency_comparison.png` | `charts.py` | Comparaison devises |
| `data/chart4_ratio_evolution.png` | `charts.py` | Évolution des ratios |
| `data/chart5_drawdown.png` | `charts.py` | Drawdown maximum |
| `data/cycle_YYYYMMDD.log` | `scheduler.py` | Log du cycle quotidien |
| `data/report_YYYYMMDD.txt` | `report.py` | Rapport quotidien |
| `state.json` | `scheduler.py` | État courant du bot |
| `trading_history.log` | `broker.py` | Journal des ordres IB |
| `backend/auroratio.db` | FastAPI startup | Base de données SQLite (local) |

---

## Variables d'environnement — récapitulatif

| Variable | Fichier | Description |
|---|---|---|
| `GMAIL_APP_PASSWORD` | `.env` | Mot de passe app Gmail pour alertes |
| `JWT_SECRET_KEY` | `.env` | Clé de signature JWT (générer aléatoirement) |
| `DATABASE_URL` | `.env` | URL PostgreSQL (ou sqlite en local) |
| `STRIPE_SECRET_KEY` | `.env` | Clé secrète Stripe |
| `STRIPE_PRICE_ID` | `.env` | ID du plan mensuel Stripe |
| `STRIPE_WEBHOOK_SECRET` | `.env` | Secret webhook Stripe |
| `SNAPTRADE_CLIENT_ID` | `.env` | Client ID SnapTrade |
| `SNAPTRADE_CONSUMER_KEY` | `.env` | Consumer Key SnapTrade |
| `SUBSCRIPTION_PRICE` | `.env` | Prix affiché (ex: 49) |
| `SUBSCRIPTION_CURRENCY` | `.env` | Devise (EUR, CHF, USD) |