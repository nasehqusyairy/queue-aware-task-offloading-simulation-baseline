# Limitations

- No claim of paper reproduction. Mapping of paper's full six offloading destinations and four DC placement remains outstanding.
- Upstream simulation_time is measured in minutes; paper reports 200 seconds.
- PureEdgeSim output does not yet have a verified parser for all requested metrics; missing values stay unavailable.
- RNG seed is not shown as configurable in selected setup; runs may not be reproducible bitwise.
- Dashboard is generated from aggregate JSON and its success-rate chart will say N/A until valid metrics exist.
- Java 25 package build passed, but runtime compatibility and GUI-free execution require end-to-end testing.
