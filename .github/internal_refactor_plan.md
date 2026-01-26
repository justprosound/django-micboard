# file: .github/internal_refactor_plan.md

# Internal Refactor Plan - Micboard Standalone (Phase 3: UI & API)

## 1. Overview & Business Logic
Micboard is a real-time RF monitoring platform.
*   **Hardware**: Chassis, Units, Chargers (with decoupled Slots).
*   **People**: Performers (User+Profile) assigned to RF Channels via `DeviceAssignment`.
*   **Compliance**: Automated frequency checks via EFIS API.
*   **Monitoring**: Real-time dashboards for battery, RF levels, and alerts.

## 2. UI Paradigm Strategy: Server-Side First (HTMX)
**Goal**: Move away from JSON-fed JS frontends. The server renders HTML; HTMX handles updates.

*   **Primary Dashboard**: Standard Django Template.
    *   *Update Mechanism*: `hx-trigger="every 5s"` polling on specific widget containers (e.g., "Device Grid").
*   **Charger Dashboard**: New Django View.
    *   *Update Mechanism*: `hx-trigger="every 10s"` on the charger grid container.
    *   *Components*: `charger_card.html`, `slot_detail.html` (partials).
    *   *Responsive Sizing*: Implement configurable `display_width_px` (User/Session setting) to scale charger cards to match physical charger dimensions. CSS Grid/Flexbox scaling required.

*   **Assignment UI**: Form-based views accessible to Technicians.
    *   *Interaction*: HTMX for inline form submission/validation without full reloads.

## 3. Domain Model (Confirmed)
*   **Hardware**: `WirelessChassis`, `WirelessUnit`, `Charger`, `ChargerSlot`.
*   **Locations**: `Building`, `Room`, `Location`.
*   **RF**: `RFChannel`, `RegulatoryDomain`, `FrequencyBand`.
*   **Monitoring**: `DeviceAssignment`, `Alert`, `MonitoringGroup`.
*   **Users**: `UserProfile`.

## 4. File Structure (Refined for UI)
```text
micboard/
├── api/
│   ├── v1/
│   │   ├── viewsets.py       # KEEP: External M2M APIs only (Chassis, Assignments)
│   │   └── urls.py
├── views/
│   ├── __init__.py
│   ├── dashboard.py          # Main index/telemetry dashboard
│   ├── charger_dashboard.py  # NEW: Charger grid view
│   ├── assignments.py        # NEW: Technician assignment management
│   └── partials.py           # NEW: HTMX partial rendering views
├── templates/
│   └── micboard/
│       ├── base.html
│       ├── index.html
│       ├── charger_dashboard.html
│       └── partials/
│           ├── device_card.html
│           ├── charger_card.html
│           └── assignment_row.html
└── ... (models/services/etc. remain as defined in Phase 2)
```

## 5. Renaming & Cleanup Plan
| Component | Action | Details |
| :--- | :--- | :--- |
| `api/v1/viewsets.py:ChargerDashboardViewSet` | **DELETE** | Replaced by `views/charger_dashboard.py`. |
| `views/dashboard/` (folder) | **FLATTEN** | Move `dashboard.py` to `views/dashboard.py`. |
| `serializers/drf.py` | **PRUNE** | Remove serializers only used for the old Charger UI. Keep those for external API. |

## 6. Implementation Steps (Phase 3)

1.  **View Restructure**:
    *   Flatten `micboard/views/` (remove subfolders where unnecessary).
    *   Create `views/charger_dashboard.py`.
2.  **Template Implementation**:
    *   Create `charger_dashboard.html` using Django Template Language (DTL).
    *   Create HTMX partials for polling updates.
3.  **API Cleanup**:
    *   Remove `ChargerDashboardViewSet` from `viewsets.py` and `urls.py`.
    *   Ensure remaining APIs (`chassis`, `assignments`) are robust for external use.
4.  **URL Configuration**:
    *   Wire up new views in `micboard/urls.py`.
    *   Ensure HTMX endpoints are accessible.
5.  **Validation**:
    *   `python manage.py check`.
