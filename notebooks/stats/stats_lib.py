"""Small statistics helpers for honest error bars on overlapping, autocorrelated data.

- n_eff: effective sample size of an AR(1)-like series, N_eff = T (1 - rho) / (1 + rho).
- ols_hac: OLS slope with a Newey-West (Bartlett) standard error. For overlapping h-tick windows the
  lag comes from the construction: use lag = h - 1.
- nonoverlap_ols: the same regression on every h-th observation only (no shared ticks between windows).
- block_stats: per-block PnL summary: mean, median, hit rate, HAC t-stat, sign-test p, concentration.
"""

import numpy as np
from scipy.stats import binomtest, norm


def ar1(x):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    d = x - x.mean()
    return float(np.dot(d[1:], d[:-1]) / np.dot(d[:-1], d[:-1]))


def n_eff(T, rho):
    return T * (1 - rho) / (1 + rho)


def _clean(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    return x[ok], y[ok]


def ols_hac(x, y, lag):
    """Slope, naive t (iid errors) and Newey-West t with Bartlett weights up to `lag`."""
    x, y = _clean(x, y)
    xd = x - x.mean()
    b = np.dot(xd, y - y.mean()) / np.dot(xd, xd)
    e = (y - y.mean()) - b * xd
    sxx = np.dot(xd, xd)
    se_naive = np.sqrt(np.dot(e, e) / (len(x) - 2) / sxx)
    u = xd * e
    s = np.dot(u, u)
    for l in range(1, int(lag) + 1):
        s += 2 * (1 - l / (lag + 1)) * np.dot(u[l:], u[:-l])
    se_hac = np.sqrt(max(s, 1e-300)) / sxx
    return dict(slope=b, t_naive=b / se_naive, t_hac=b / se_hac, n=len(x))


def nonoverlap_ols(x, y, h, start=0):
    """OLS on every h-th observation; returns slope, t and n (iid t is fine: windows don't overlap)."""
    x, y = _clean(np.asarray(x, float)[start::h], np.asarray(y, float)[start::h])
    if len(x) < 4:
        return dict(slope=np.nan, t=np.nan, n=len(x))
    r = ols_hac(x, y, 0)
    return dict(slope=r["slope"], t=r["t_naive"], n=r["n"])


def hac_mean_t(v, lag=2):
    """t-stat of a mean with a Newey-West standard error (for block PnL, which can be autocorrelated)."""
    v = np.asarray(v, float)
    v = v[~np.isnan(v)]
    n, m = len(v), v.mean()
    d = v - m
    s = np.dot(d, d)
    for l in range(1, lag + 1):
        s += 2 * (1 - l / (lag + 1)) * np.dot(d[l:], d[:-l])
    se = np.sqrt(s / n) / np.sqrt(n)
    return float(m / se) if se > 0 else np.nan


def sign_test_p(v, alternative="greater"):
    v = np.asarray(v, float)
    v = v[(~np.isnan(v)) & (v != 0)]
    if len(v) == 0:
        return np.nan
    return float(binomtest(int((v > 0).sum()), len(v), 0.5, alternative=alternative).pvalue)


def block_stats(v):
    v = np.asarray(v, float)
    tot = v.sum()
    return dict(total=tot, mean=v.mean(), median=float(np.median(v)), hit_rate=float((v > 0).mean()),
                t_hac=hac_mean_t(v), sign_p=sign_test_p(v),
                top_block_share=float(np.max(v) / tot) if tot > 0 else np.nan,
                top3_share=float(np.sort(v)[-3:].sum() / tot) if tot > 0 else np.nan)


def fisher_p(rs, ns):
    """Combine per-day correlations (each from n independent obs) with Fisher z + Stouffer. Two-sided p."""
    zs = [np.arctanh(np.clip(r, -0.999999, 0.999999)) * np.sqrt(max(n - 3, 1)) for r, n in zip(rs, ns)]
    Z = np.sum(zs) / np.sqrt(len(zs))
    return float(2 * norm.sf(abs(Z))), float(Z)


def benjamini_hochberg(p, q=0.05):
    p = np.asarray(p, float)
    order = np.argsort(p)
    m = len(p)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    k = np.max(np.where(passed)[0]) + 1 if passed.any() else 0
    keep = np.zeros(m, bool)
    keep[order[:k]] = True
    return keep
