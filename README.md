# Belgische kaartupdates publiceren

Deze map bevat de automatische broncode voor een publieke GitHub-repository. Je hoeft zelf geen kaarten te bouwen of bestanden te uploaden nadat de repository is ingericht. De workflow haalt op de 1e en 15e van elke maand het actuele België-extract van Geofabrik op, bouwt de MotoLimiet SQLite-database, controleert haar en publiceert `belgium-limits.db.gz` met `manifest.json` als één GitHub Release. Een handmatige start kan via **Actions → Publish Belgium map → Run workflow**.

## Eenmalige inrichting

1. Maak een **publieke** GitHub-repository, bijvoorbeeld `motolimiet-maps`. Zet de inhoud van het meegeleverde publicatiepakket in de hoofdmap van die repository, inclusief `.github/workflows/publish-belgium-map.yml` en de drie Python-scripts in `tools/`. Zet geen private ondertekeningssleutel of APK in deze repository.
2. Laat bij de repository onder **Settings → Actions → General → Workflow permissions** schrijfpermissies voor de workflow toe, zodat de ingebouwde `GITHUB_TOKEN` een Release en een kleine statuscommit kan maken. Een beveiligde standaardbranch kan de statuscommit blokkeren; stel de branchbeveiliging in overeenstemming met dit doel in.
3. Start de workflow de eerste keer handmatig. Controleer de jobstappen en de Release. Verwacht twee bestanden: `manifest.json` en `belgium-limits.db.gz`. De brongegevens zijn groot; GitHub Actions heeft netwerk- en opslagruimte nodig.
4. Stel in MotoLimiet onder **Instellingen → Kaartupdates → Updateadres instellen** deze URL in (vervang `GEBRUIKER/REPO`):

   `https://github.com/GEBRUIKER/REPO/releases/latest/download/manifest.json`

Vanaf dan doet de app bij iedere start een kleine HTTPS-controle. De daadwerkelijke database wordt alleen na jouw keuze op een ongemeten netwerk gedownload. Tijdens een rit wordt de kaart niet vervangen.

## Publicatie en beheer

De gepubliceerde database is afgeleid van © OpenStreetMap contributors en wordt onder ODbL 1.0 beschikbaar gesteld. De Release vermeldt de licentie, de bron Geofabrik en de omzettingscode. De repository en releases zijn publiek toegankelijk. De GitHub-workflow gebruikt `osmium==4.3.1`, een SQLite-controle en een minimum van 3.000.000 wegsegmenten. Bij een mislukte run blijft de vorige Release bereikbaar. Een kleine statuscommit na een geslaagde publicatie houdt activiteit in de publieke repository; GitHub kan geplande workflows bij 60 dagen inactiviteit anders uitschakelen. Controleer periodiek de Actions-status, vooral wanneer de app meldt dat de updatebron ouder dan 45 dagen is.

GitHub-documentatie: https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases en https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows. Bron: https://download.geofabrik.de/europe/belgium.html. Licentie: https://www.openstreetmap.org/copyright.
