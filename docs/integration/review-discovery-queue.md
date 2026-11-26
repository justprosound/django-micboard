---
title: "Review discovered devices"
description: "Approve, reject or skip queued discoveries and acknowledge device movements in the admin."
type: how-to
audience: staff
---
How devices get into the queue and how they are matched is explained in [Device discovery workflow](discovery-workflow.md).

## Review the queue

1. Open the Django admin and go to **Micboard > Discovery queue**.
2. Filter by status (`pending` shows what needs a decision), manufacturer or conflict flags. The **Conflicts** column and **Conflict Analysis** show what a row collided with, such as an existing device or an IP conflict.
3. Select one or more rows and choose an action:
   - **Approve selected devices for import** creates or updates the chassis or charger and marks the rows imported. Approve at most 100 rows at a time.
   - **Reject selected devices** marks pending rows rejected and keeps them for the audit trail.
   - **Mark as duplicate (no import)** marks pending rows as duplicates without importing.

Each action records the reviewer and the time. Reject and duplicate only change rows that are still `pending`.

## Acknowledge movements

1. Go to **Micboard > Device movement log**. Each row shows the old and new IP or location.
2. Select the rows and choose **Acknowledge selected movements**.

## Fix a device that keeps being queued as a conflict

- If the IP is held by a different device, correct the address on one of the two chassis or remove the stale record, then run discovery again.
- If a device is matched to the wrong chassis, compare the serial number and MAC address on the queue row with the chassis. A serial and MAC that belong to two different chassis are always queued for review.
