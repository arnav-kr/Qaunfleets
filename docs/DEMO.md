# Demonstration

1. Open http://127.0.0.1:8767/. Recorded QCloud + Opt execution shows six projected-ready requests, an 18.4 kW peak below 25.6 kW and an ₹18.82 projected bill.
2. Select a vehicle row. Compare delivered/requested kWh, confirmed departure, predicted unplug proxy, finish and allocation. Progress is top-up energy, not battery SOC.
3. Move the clock to 01:00, select V2, open **Change conditions**, choose **Vehicle leaves now** and apply. The **Early-departure example** button prepares this same event directly. V2 retains 6.48 kWh delivered and has a 12.96 kWh departure shortfall. Five requests remain satisfied. Past charging stays solid; future visits are outlined.
4. Show site loading and partial-service cost. Reduced expenditure after a departure is not a saving at equivalent service. Bay hold/release, revised deadline and building-load increase are additional events.
5. Open **Execution details** for circuit/backend/shot evidence, selected QUBO visits, solver mode, validation and matched classical comparisons. **Generate plan** executes the configured hybrid pipeline with local credentials. Recorded playback is labeled separately.
6. Open **3D depot** for schedule-driven movement. The timeline remains the operational record; staff clearance is assumed between visits unless a bay hold is supplied.

Reset confirms before discarding history. Export retains the current session branch. Prices use synthetic INR demo rates (numeric assumptions unchanged; no foreign-exchange conversion). The predictor uses workplace session ends as an unplug-time proxy. Automatic vehicle-linked clearance, unexpected arrivals and optimal partial-service recovery remain future work.
