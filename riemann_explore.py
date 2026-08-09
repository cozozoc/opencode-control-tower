"""
Phase 1: Riemann Zeta Function Numerical Exploration
- Compute non-trivial zeros on the critical line
- Verify known results
- Explore patterns
"""
import mpmath as mp
import sys

mp.mp.dps = 50  # 50 decimal digits precision

def xi_on_critical_line(t):
    """Compute ξ(1/2 + it) which is real-valued on the critical line."""
    s = 0.5 + 1j * t
    xi = 0.5 * s * (s - 1) * mp.pi**(-s/2) * mp.gamma(s/2) * mp.zeta(s)
    return float(xi.real)

# ===== Part 1: Verify known zeros =====
print("=" * 60)
print("PART 1: Verify known non-trivial zeros at Re(s) = 1/2")
print("=" * 60)

known_zeros_imag = [14.134725, 21.022040, 25.010857, 30.424876, 32.935061, 37.586178]

for gamma in known_zeros_imag:
    s = 0.5 + 1j * gamma
    zeta_val = mp.zeta(s)
    print(f"  s = 0.5 + {gamma:.6f}i  =>  |ζ(s)| = {float(abs(zeta_val)):.2e}")

# ===== Part 2: Find zeros via sign changes in ξ(t) =====
print("\n" + "=" * 60)
print("PART 2: Find zeros by scanning ξ(1/2 + it) for sign changes")
print("=" * 60)

def find_zeros_upto(max_t, step=0.25):
    """Find zeros of ξ(1/2 + it) by detecting sign changes and refining."""
    zeros = []
    t_prev = 0.0
    xi_prev = xi_on_critical_line(t_prev)
    
    t = step
    while t <= max_t:
        xi_curr = xi_on_critical_line(t)
        if xi_prev * xi_curr < 0:  # sign change
            try:
                zero = mp.findroot(xi_on_critical_line, (t - step + t) / 2)
                zeros.append(float(zero))
            except Exception:
                pass
        t_prev = t
        xi_prev = xi_curr
        t += step
    
    return zeros

zeros_50 = find_zeros_upto(50)
print(f"Found {len(zeros_50)} zeros in t ∈ [0, 50]:")
for i, z in enumerate(zeros_50):
    print(f"  Zero #{i+1}: t = {z:.10f}")

# ===== Part 3: Zero spacing statistics =====
print("\n" + "=" * 60)
print("PART 3: Zero spacing statistics")
print("=" * 60)

spacings = [zeros_50[i+1] - zeros_50[i] for i in range(len(zeros_50)-1)]
print(f"  Min spacing: {min(spacings):.6f}")
print(f"  Max spacing: {max(spacings):.6f}")
print(f"  Mean spacing: {sum(spacings)/len(spacings):.6f}")

# Expected mean spacing at height T: 2π / log(T/(2π))
import math
for i, z in enumerate([zeros_50[0], zeros_50[len(zeros_50)//2], zeros_50[-1]]):
    expected = 2 * math.pi / math.log(z / (2 * math.pi))
    print(f"  At t = {z:.2f}, expected mean spacing = {expected:.6f}")

# ===== Part 4: Explore off the critical line =====
print("\n" + "=" * 60)
print("PART 4: Check |ζ(s)| off the critical line")
print("=" * 60)

# Check a grid around the first zero
zero1 = zeros_50[0]
print(f"Exploring around first zero t = {zero1:.6f}:")
for sigma in [0.3, 0.4, 0.5, 0.6, 0.7]:
    for dt in [-0.5, -0.2, 0, 0.2, 0.5]:
        s = sigma + 1j * (zero1 + dt)
        val = float(abs(mp.zeta(s)))
        marker = " <-- MIN" if dt == 0 and sigma == 0.5 else ""
        print(f"  σ={sigma:.1f}, t={zero1+dt:.3f}: |ζ(s)| = {val:.6e}{marker}")

print("\nDone.")
