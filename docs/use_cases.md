# Micboard Use Cases and Views

Micboard provides a flexible dashboard for monitoring wireless microphone receivers. It supports various views to organize and filter devices based on different criteria.

## Dashboard Views

### 1. Main Dashboard (Index)
**URL:** `/`
**Description:** The landing page providing a high-level overview.
**Features:**
- Summary counts of devices and groups.
- Links to all other views (Buildings, Rooms, Users, Manufacturers).
- Displays all active receivers visible to the user.

### 2. Device Type View
**URL:** `/view/type/<device_type>/`
**Description:** Filters receivers by their model/type (e.g., `ulxd`, `axient`).
**Use Case:** Monitoring specific hardware fleets.
**Optional Filters:** `?manufacturer=<code>`

### 3. Building View
**URL:** `/view/building/<building_name>/`
**Description:** Displays all receivers located in a specific building.
**Use Case:** Facility-level monitoring.
**Optional Filters:** `?manufacturer=<code>`

### 4. Room View
**URL:** `/view/room/<building_name>/<room_name>/`
**Description:** Granular view for a specific room within a building.
**Use Case:** Monitoring a specific studio or stage.
**Optional Filters:** `?manufacturer=<code>`

### 5. User View
**URL:** `/view/user/<username>/`
**Description:** Shows receivers assigned to a specific user.
**Use Case:** Personal monitoring dashboard for audio engineers.
**Optional Filters:** `?manufacturer=<code>`

### 6. Priority View
**URL:** `/view/priority/<priority>/`
**Description:** Filters receivers based on assignment priority.
**Use Case:** Focusing on critical devices (e.g., "High" priority).
**Optional Filters:** `?manufacturer=<code>`

## Configuration
Views are dynamically generated based on the data in the database. To utilize these views:
1. **Define Locations:** Create Building and Room objects in the admin panel.
2. **Assign Devices:** Edit Receivers to assign them to specific Buildings and Rooms.
3. **User Assignments:** Assign Channels to Users with specific priorities.

## Filtering
Most views support an optional `manufacturer` query parameter to further filter the displayed devices by manufacturer code (e.g., `?manufacturer=shure`).
