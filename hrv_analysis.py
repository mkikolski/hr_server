"""
HRV analysis utilities for resonant frequency detection.
"""

import numpy as np


def compute_baseline_hr(hr_values: list[int]) -> float:
    """Compute the mean heart rate from a list of HR readings.

    Args:
        hr_values: List of heart rate values in BPM.

    Returns:
        Mean heart rate as a float.
    """
    if not hr_values:
        return 0.0
    return float(np.mean(hr_values))


def compute_hrv_amplitude(rr_intervals: list[float]) -> float:
    """Compute the HRV amplitude for a segment of RR intervals.

    HRV amplitude is measured as the difference between the maximum and minimum
    instantaneous heart rate derived from the RR intervals. This reflects the
    magnitude of heart rate oscillation during paced breathing.

    Args:
        rr_intervals: List of RR interval values in milliseconds.

    Returns:
        HRV amplitude (max HR - min HR) in BPM. Returns 0.0 if insufficient data.
    """
    if len(rr_intervals) < 2:
        return 0.0

    # Convert RR intervals (ms) to instantaneous heart rate (BPM)
    hr_values = [60000.0 / rr for rr in rr_intervals if rr > 0]

    if len(hr_values) < 2:
        return 0.0

    return float(max(hr_values) - min(hr_values))


def compute_resonant_frequency(
    segments: dict[float, list[float]],
) -> tuple[float, dict[float, float]]:
    """Determine the resonant breathing frequency from paced-breathing segments.

    For each breathing rate, the HRV amplitude is computed from the collected
    RR intervals. The rate with the highest amplitude is the resonant frequency.

    Args:
        segments: Dict mapping breathing rate (breaths/min) to a list of
                  RR intervals (ms) collected during that segment.

    Returns:
        A tuple of (resonant_frequency_bpm, amplitudes_dict).
        resonant_frequency_bpm is the breathing rate with the highest HRV amplitude.
        amplitudes_dict maps each breathing rate to its computed HRV amplitude.
    """
    amplitudes: dict[float, float] = {}

    for rate, rr_intervals in segments.items():
        amplitudes[rate] = compute_hrv_amplitude(rr_intervals)

    if not amplitudes:
        return 6.0, amplitudes  # Fallback to common resonant frequency

    best_rate = max(amplitudes, key=amplitudes.get)
    return best_rate, amplitudes


def compute_rmssd(rr_intervals: list[float]) -> float:
    """Compute RMSSD (Root Mean Square of Successive Differences) from RR intervals.

    This is a standard time-domain HRV metric displayed on the control panel.

    Args:
        rr_intervals: List of RR intervals in milliseconds.

    Returns:
        RMSSD value in milliseconds.
    """
    if len(rr_intervals) < 2:
        return 0.0

    diffs = np.diff(rr_intervals)
    return float(np.sqrt(np.mean(diffs ** 2)))


def compute_sdnn(rr_intervals: list[float]) -> float:
    """Compute SDNN (Standard Deviation of NN intervals) from RR intervals.

    Args:
        rr_intervals: List of RR intervals in milliseconds.

    Returns:
        SDNN value in milliseconds.
    """
    if len(rr_intervals) < 2:
        return 0.0
    return float(np.std(rr_intervals, ddof=1))
