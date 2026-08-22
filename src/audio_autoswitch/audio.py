"""Windows audio endpoint queries and default-device switching (WASAPI/COM)."""

from __future__ import annotations

from dataclasses import dataclass

import comtypes
from _ctypes import COMError
from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
from pycaw.constants import (
    CLSID_CPolicyConfigClient,
    CLSID_MMDeviceEnumerator,
    DEVICE_STATE,
    EDataFlow,
    ERole,
    STGM,
)
from pycaw.api.policyconfig import IPolicyConfig

# Roles Windows tracks separately: "Default Device" (console + multimedia)
# and "Default Communication Device".
ROLE_DEFAULT = (ERole.eConsole, ERole.eMultimedia)
ROLE_COMMUNICATIONS = (ERole.eCommunications,)

# PKEY_Device_FriendlyName -> "Microphone (fifine Microphone)"
_PKEY_FRIENDLY_NAME = "{A45C254E-DF1C-4EFD-8020-67D146A850E0} 14"


@dataclass(frozen=True)
class Device:
    id: str
    name: str


def _enumerator():
    return comtypes.CoCreateInstance(
        CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER
    )


def _friendly_name(dev) -> str:
    store = dev.OpenPropertyStore(STGM.STGM_READ.value)
    for i in range(store.GetCount()):
        pk = store.GetAt(i)
        if str(pk).upper() != _PKEY_FRIENDLY_NAME:
            continue
        value = store.GetValue(pk)
        name = value.GetValue()
        value.clear()
        return str(name)
    return "Unknown device"


def list_microphones() -> list[Device]:
    """Active capture endpoints, in the order Windows reports them."""
    collection = _enumerator().EnumAudioEndpoints(
        EDataFlow.eCapture.value, DEVICE_STATE.ACTIVE.value
    )
    devices = []
    for i in range(collection.GetCount()):
        dev = collection.Item(i)
        devices.append(Device(dev.GetId(), _friendly_name(dev)))
    return devices


def active_microphone_ids() -> set[str]:
    """Cheap availability check: ids only, no property-store reads."""
    collection = _enumerator().EnumAudioEndpoints(
        EDataFlow.eCapture.value, DEVICE_STATE.ACTIVE.value
    )
    return {collection.Item(i).GetId() for i in range(collection.GetCount())}


def default_microphone_id(role: ERole = ERole.eConsole) -> str | None:
    try:
        dev = _enumerator().GetDefaultAudioEndpoint(
            EDataFlow.eCapture.value, role.value
        )
    except (OSError, COMError):
        return None  # no capture device assigned to this role
    return dev.GetId()


def default_microphone_ids() -> tuple[str | None, str | None]:
    """The endpoints Windows is on right now, as (Default, Default Communication)."""
    return (
        default_microphone_id(ERole.eConsole),
        default_microphone_id(ERole.eCommunications),
    )


def set_default_microphone(device_id: str, roles=ROLE_DEFAULT) -> None:
    policy = comtypes.CoCreateInstance(
        CLSID_CPolicyConfigClient, IPolicyConfig, comtypes.CLSCTX_ALL
    )
    for role in roles:
        # COMError is not an OSError, so translate it: callers handle one type.
        try:
            hr = policy.SetDefaultEndpoint(device_id, role.value)
        except COMError as exc:
            raise OSError(f"SetDefaultEndpoint({role.name}) failed: {exc}") from exc
        if hr != 0:
            raise OSError(f"SetDefaultEndpoint({role.name}) failed: {hr:#010x}")
