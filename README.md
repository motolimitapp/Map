# MotoLimiet Belgium map pipeline

Deze publieke repository bouwt de canonical Belgische kaartdatabase voor MotoLimiet.

## Architectuur

Er is nog maar één kaartgenerator. De gevalideerde v3-build wordt gebruikt voor:

- online kaartupdates van bestaande MotoLimiet-installaties;
- de embedded/factory map van een toekomstige APK-release.

De embedded map is dus geen afzonderlijke kaartbron: ze is een snapshot van een eerder gevalideerd artefact uit deze pipeline.

## Build en publicatie

Workflow: `.github/workflows/publish-belgium-map.yml`

Triggers:

- handmatig via **Actions → Build and publish Belgium v3 map → Run workflow**;
- automatisch op de 1e en 15e om 04:17 in `Europe/Brussels`.

De pipeline:

1. installeert de vastgelegde Python dependencies;
2. voert de v3-regressietests uit;
3. downloadt `https://download.geofabrik.de/europe/belgium-latest.osm.pbf`;
4. downloadt een volledige AWV/MOW-snapshot;
5. bouwt de OSM v3-database;
6. vergelijkt OSM met AWV en bouwt de quality map;
7. voert volledige kaart- en SQLite-validatie uit;
8. maakt een deterministische gzip en SHA-256;
9. genereert `manifest.json`;
10. bewaart de gevalideerde candidate als Actions artifact;
11. publiceert pas daarna naar het vaste live kanaal `map-v3-live`.

## Live update URL

MotoLimiet 0.3.10 kan als updatebron gebruiken:

`https://github.com/motolimitapp/Map/releases/download/map-v3-live/manifest.json`

Manifest en kaart staan bewust onder dezelfde HTTPS-host en dezelfde release-directory, omdat de 0.3.10 updateclient dit valideert.

De pipeline uploadt eerst het nieuwe kaartbestand en vervangt daarna `manifest.json`. De huidige en vorige kaartasset blijven behouden.

## Embedded/factory map

Voor een nieuwe Android-release neem je het gevalideerde `belgium-limits-<run-id>-<attempt>.db.gz` van een succesvolle build, hernoem je dit naar `belgium-limits.db.gz` en plaats je het onder `app/src/main/assets/` in het Android-project.

## Recovery

De repository-state vóór de v3-integratie van 6 oktober 2026 is bewaard op branch:

`backup/pre-v3-pipeline-2026-10-06`

De oude v2-tools blijven voorlopig in de repository als historische referentie, maar worden niet meer door de actieve workflow gebruikt.

## Bronnen

- OpenStreetMap Belgium extract via Geofabrik — ODbL
- MOW/AWV `Afgeleide_snelheidsregimes`

De pipeline behandelt bronconflicten conservatief. Expliciete conflicten en variabele regimes worden niet als zekere numerieke snelheidslimiet gepubliceerd.
