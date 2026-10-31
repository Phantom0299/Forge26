# IMD & CWC Weather Warning & Road Action Protocol
## Impact-Based Flash Flood, Extreme Rainfall & Mountain Highway Closure Matrix
**Collaborating Agencies:** India Meteorological Department (IMD) & Central Water Commission (CWC)
**Scope:** Eastern Himalayan River Basins (Kameng, Tawang Chu, Brahmaputra Tributaries)

---

### 1. Rainfall Thresholds and Highway Advisory Levels

Mountain roads in northeastern states (Assam, Arunachal Pradesh, Sikkim) are governed by cumulative precipitation thresholds:

| IMD Alert Level | 24-Hour Rainfall Threshold | Soil Saturation Index (SSI) | Landslide Hazard Probability | Highway Traffic Action |
|---|---|---|---|---|
| **Green (No Warning)** | $< 64.5$ mm | $< 50\%$ | $< 15\%$ | Normal operations; regular road maintenance |
| **Yellow (Watch / Be Aware)** | $64.5 - 115.5$ mm (Heavy Rain) | $50\% - 70\%$ | $15\% - 45\%$ | Night driving restricted for buses/HTVs between 19:00 - 05:00 hrs |
| **Orange (Alert / Be Prepared)** | $115.6 - 204.4$ mm (Very Heavy Rain) | $70\% - 85\%$ | $45\% - 75\%$ | Suspension of commercial transit; convoy movement only under BRO escort |
| **Red (Warning / Take Action)** | $> 204.4$ mm (Extremely Heavy Rain) | $> 85\%$ | $> 75\%$ | Mandatory complete road closure; evacuation of low-lying riverbank sectors |

---

### 2. 72-Hour Cumulative Rainfall (Antecedent Rainfall Index)

The probability of catastrophic debris flows increases exponentially when cumulative 3-day rainfall exceeds **350 mm**, regardless of 24-hour rate.

- **Trigger Threshold:** If 72-hour precipitation $\ge 300$ mm AND slope angle $\ge 35^\circ$, all culverts and river crossing causeways are placed under continuous physical or sensor-based watch.
- **Debris Flow / Mudslide Early Warning:**
  - Water in roadside mountain streams turning from clear to heavily turbid (chocolate brown) indicates upstream slope collapse or damming.
  - Immediate action: Halt traffic at least 1,000 meters clear of the bridge or culvert fan area.

---

### 3. Flash Flood Inundation & SAR Satellite Validation Protocols

When Sentinel-1 SAR flood processor registers backscatter drops ($< -18$ dB in VV polarization) on road segments:
1. Ground water depth is assumed $\ge 0.4$ meters.
2. No vehicle with wheel diameter $< 1.0$ meter is permitted to cross flowing causeways where water depth exceeds 0.25 meters.
3. Automated warning sent via RouteX API to all connected vehicle telemetry units within a 25 km corridor buffer.
