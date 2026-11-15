"""The installer's engine choice (0.3.0 on the office PC): a GPU only when the driver and card can run CUDA 12, found
wherever the driver put nvidia-smi, and never the 2 GB CUDA download on an old card or driver."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "release" / "gpu_check.ps1"

pytestmark = pytest.mark.skipif(shutil.which("powershell") is None, reason="Windows PowerShell")


def choose(card: dict | None) -> dict:
    literal = "$null" if card is None else "@{" + "; ".join(f"{k} = '{v}'" for k, v in card.items()) + "}"
    command = f". '{SCRIPT}'; Select-Engine {literal} | ConvertTo-Json -Compress"
    done = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True, text=True, check=True, timeout=60,
    )  # fmt: skip
    return json.loads(done.stdout)


def test_no_card_takes_the_cpu() -> None:
    assert choose(None)["Gpu"] is False


def test_the_office_pc_gt_730_on_driver_391_takes_the_cpu_and_says_why() -> None:
    answer = choose({"Name": "NVIDIA GeForce GT 730", "Driver": "391.35", "Compute": ""})
    assert answer["Gpu"] is False
    assert "391.35" in answer["Why"] and "527.41" in answer["Why"]


def test_a_kepler_card_on_a_new_driver_takes_the_cpu() -> None:
    answer = choose({"Name": "NVIDIA GeForce GT 730", "Driver": "475.14", "Compute": "3.5"})
    assert answer["Gpu"] is False
    answer = choose({"Name": "NVIDIA Tesla K80", "Driver": "538.15", "Compute": "3.7"})
    assert answer["Gpu"] is False and "3.7" in answer["Why"]


@pytest.mark.parametrize(
    "card",
    [
        {"Name": "NVIDIA GeForce RTX 5080", "Driver": "576.02", "Compute": "12.0"},
        {"Name": "NVIDIA GeForce RTX 3070 Ti Laptop GPU", "Driver": "596.08", "Compute": "8.6"},
        {"Name": "NVIDIA GeForce GTX 1060", "Driver": "528.02", "Compute": ""},
    ],
)
def test_a_card_and_driver_that_run_cuda_12_take_the_gpu(card: dict) -> None:
    assert choose(card)["Gpu"] is True


def test_an_unreadable_driver_takes_the_cpu() -> None:
    assert choose({"Name": "NVIDIA something", "Driver": "", "Compute": ""})["Gpu"] is False


def test_windows_driver_numbers_read_as_nvidia_versions() -> None:
    command = (
        f". '{SCRIPT}'; @('23.21.13.9135', '31.0.15.2802', '32.0.15.7602') | "
        "ForEach-Object { ConvertFrom-WindowsDriverVersion $_ } | ConvertTo-Json -Compress"
    )
    done = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True, text=True, check=True, timeout=60,
    )  # fmt: skip
    assert json.loads(done.stdout) == ["391.35", "528.02", "576.02"]


def test_this_pc_is_read_from_its_driver() -> None:
    """The real lookup on whatever PC runs the tests: a card found reads a name and a driver."""
    command = f". '{SCRIPT}'; Read-NvidiaCard | ConvertTo-Json -Compress"
    done = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True, text=True, check=True, timeout=120,
    )  # fmt: skip
    if not done.stdout.strip():
        pytest.skip("no NVIDIA card on this PC")
    card = json.loads(done.stdout)
    assert "NVIDIA" in card["Name"] and card["Driver"]
