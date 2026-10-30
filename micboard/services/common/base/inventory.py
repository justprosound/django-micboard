"""The device list a manufacturer client returns, and whether it is the whole inventory."""

from typing import Any


class DeviceInventory(list[dict[str, Any]]):
    """A device list that says whether the client had to drop anything from the response.

    A client sets `complete` to False when it skipped a malformed item or could not read
    the response shape. The poll still persists the devices that were read, but never
    treats the list as the vendor's whole inventory, so no absent chassis goes offline.
    """

    def __init__(self, devices: list[dict[str, Any]] | None = None, *, complete: bool = True):
        super().__init__(devices or [])
        self.complete = complete
