"""
Phase 2: Zero spacing statistics and GUE comparison
- Compute many zeros on critical line
- Normalize spacings
- Compare with GUE pair correlation: 1 - (sin(πx)/πx)^2
- Nearest-neighbor spacing distribution
"""
import mpmath as mp
import math, json, sys

mp.mp.dps = 50

def xi_t(t):
    """ξ(1/2 + it) — real-valued"""
    s = 0.5 + 1j * t
    xi = 0.5 * s * (s - 1) * mp.pi**(-s/2) * mp.gamma(s/2) * mp.zeta(s)
    return float(xi.real)

def find_zeros_upto(max_t, step=0.5):
    """Find zeros of ξ(1/2 + it) by sign changes + findroot."""
    zeros = []
    t_prev = 0.0
    xi_prev = xi_t(t_prev)
    t = step
    while t <= max_t:
        xi_curr = xi_t(t)
        if xi_prev * xi_curr < 0:
            try:
                zero = mp.findroot(xi_t, (t - step + t) / 2)
                zeros.append(float(zero))
            except Exception:
                pass
        t_prev, xi_prev = t, xi_curr
        t += step
    return zeros

print("Computing zeros up to t = 500 (this may take a moment)...")
zeros = find_zeros_upto(500, step=0.25)
n = len(zeros)
print(f"Found {n} zeros")

# Normalize spacings: mean spacing at height T is ~ 2π / log(T/(2π))
# We normalize so mean = 1
normalized_spacings = []
for i in range(n - 1):
    t_mid = (zeros[i] + zeros[i+1]) / 2
    mean_spacing = 2 * math.pi / math.log(t_mid / (2 * math.pi)) if t_mid > 2*math.pi else 2*math.pi
    normalized_spacings.append((zeros[i+1] - zeros[i]) / mean_spacing)

# ===== Pair correlation histogram =====
# GUE pair correlation: g(x) = 1 - (sin(πx)/(πx))^2
# For small x: g(x) ≈ (π²/3)x²  →  "level repulsion"
print("\n=== Pair Correlation (compare with GUE) ===")

def gue_pair_corr(x):
    if abs(x) < 1e-12:
        return (math.pi**2 / 3) * x**2
    return 1 - (math.sin(math.pi * x) / (math.pi * x))**2

# Compute spacings between pairs separated by k
k = 1  # nearest neighbor
diffs = []
for i in range(len(zeros) - k):
    t_mid = (zeros[i] + zeros[i+k]) / 2
    mean_spacing = 2 * math.pi / math.log(t_mid / (2 * math.pi)) if t_mid > 2*math.pi else 2*math.pi
    diffs.append((zeros[i+k] - zeros[i]) / mean_spacing)

# Histogram
nbins = 30
max_x = 3.0
bin_width = max_x / nbins
hist = [0] * nbins
for d in diffs:
    if 0 <= d < max_x:
        idx = int(d / bin_width)
        if idx < nbins:
            hist[idx] += 1

# Normalize histogram
total = sum(hist)
print(f"{'x':>8s}  {'observed':>10s}  {'GUE pred':>10s}  {'ratio':>10s}")
print("-" * 45)
for b in range(nbins):
    x = (b + 0.5) * bin_width
    obs = hist[b] / total / bin_width if total > 0 else 0
    pred = gue_pair_corr(x)
    ratio = obs / pred if pred > 0.001 else 0
    print(f"{x:8.4f}  {obs:10.6f}  {pred:10.6f}  {ratio:10.3f}")

# ===== Key statistical tests =====
print("\n=== Statistical Summary ===")
mean_norm = sum(normalized_spacings) / len(normalized_spacings)
print(f"Mean normalized spacing: {mean_norm:.6f} (expected: 1.0)")

# Level repulsion: probability of very small spacing
small_threshold = 0.05
small_count = sum(1 for s in normalized_spacings if s < small_threshold)
print(f"Fraction with spacing < {small_threshold}: {small_count}/{len(normalized_spacings)} = {small_count/len(normalized_spacings):.4f}")
print(f"GUE prediction for x<{small_threshold}: ~{gue_pair_corr(0.025) * small_threshold:.4f}")

# Nearest-neighbor spacing distribution (Wigner surmise)
print("\n=== Nearest-Neighbor Spacing Distribution ===")
# Wigner surmise for GUE: P(s) = (32/π²) s² exp(-4s²/π)
def wigner_surmise(s):
    return (32 / math.pi**2) * s**2 * math.exp(-4 * s**2 / math.pi)

nn_bins = 20
nn_max = 3.0
nn_width = nn_max / nn_bins
nn_hist = [0] * nn_bins
for s in normalized_spacings:
    if 0 <= s < nn_max:
        idx = int(s / nn_width)
        if idx < nn_bins:
            nn_hist[idx] += 1

nn_total = sum(nn_hist)
print(f"{'s':>8s}  {'observed':>10s}  {'Wigner':>10s}")
print("-" * 35)
for b in range(nn_bins):
    s = (b + 0.5) * nn_width
    obs = nn_hist[b] / nn_total / nn_width if nn_total > 0 else 0
    wig = wigner_surmise(s)
    print(f"{s:8.4f}  {obs:10.6f}  {wig:10.6f}")

print("\nDone.")
