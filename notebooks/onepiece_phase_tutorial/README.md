# OnePiece Cu/Ga Phase Tutorial Notebooks

Diese Notebook-Serie startet bei den HDF-Dateien aus OnePiece und zeigt Schritt
für Schritt, wie die Tabellen unter dem Bulk/Oberflächen-Multiplot entstehen.

## Reihenfolge

1. `00_hdf_onepiece_pandas_ase_intro.ipynb`
   - lädt eine HDF-Datei mit `pd.read_hdf(filename, key="df")`
   - erklärt `pandas.DataFrame`, OnePiece-Adapter und ASE-Strukturspalten
   - zeigt erste Filter-, Sortier- und Descriptor-Befehle

2. `01_bulk_phase_table_from_hdf.ipynb`
   - lädt `CuGabulk_oxide.hdf`
   - baut das Temperatur- und `pH2O/pH2`-Raster
   - evaluiert Bulk-Energieausdrücke
   - erzeugt `tutorial_bulk_transition_summary.csv`

3. `02_surface_phase_tables_from_hdf.ipynb`
   - lädt `CuGasurf_100.hdf`, `CuGasurf_110.hdf`, `CuGasurf_111.hdf`,
     `CuGasurf_211.hdf`
   - berechnet korrigierte Oberflächenenergien pro Fläche
   - erzeugt pro Miller-Index und kombiniert stabile Phasentabellen

4. `03_multiplot_transition_tables.ipynb`
   - kombiniert Bulk- und Oberflächen-Summaries
   - formt das gemeinsame Tabellenschema für den Multiplot
   - speichert `tutorial_bulk_surface_transition_phase_summary_extended.csv`

## Inputs

Die Notebooks lesen den Datenpfad aus der Umgebungsvariable
`ONEPIECE_DATA_ROOT` (Standardwert: `data/surface_alloys` relativ zum
Arbeitsverzeichnis):

```bash
export ONEPIECE_DATA_ROOT="/pfad/zu/surface_alloys"
```

Der Pfad ist oben in jedem Notebook in `DATA_ROOT` definiert.

## Outputs

Die Tutorial-Outputs werden nach `notebooks/phase_diagram_outputs` unterhalb des
Projektstammverzeichnisses geschrieben (`ONEPIECE_PROJECT_ROOT`, Standardwert:
aktuelles Arbeitsverzeichnis), damit sie neben den bereits erzeugten finalen
Diagrammen liegen.
