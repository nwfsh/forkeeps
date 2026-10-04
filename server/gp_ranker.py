"""Gaussian-process preference learning: the same picks and features as ranker.Ranker, but the
"how much I like it" score is any smooth function of the features instead of a weighted sum.

Bradley-Terry adds up a fixed amount per feature, so it can't learn that chin down matters more
with a soft smile than with a grin, or a best angle in between without the hand-made curve
features. A GP can: it learns a latent score g(photo) with an RBF kernel over the features, and
a pick says g(winner) > g(loser) (Chu & Ghahramani 2005). On avery's 51 test picks it agreed with
her 73% of the time against Bradley-Terry's 65%, with the same 7 features (small sample).

Fitted with the Laplace approximation (Rasmussen & Williams, algorithm 3.1) on pairs, using the
preference kernel k((a,b),(c,d)) = k(a,c) + k(b,d) - k(a,d) - k(b,c). The kernel's length scale
and size are chosen by cross-validation on the picks themselves.
"""
import random
from typing import Optional

import numpy as np

from ranker import FEATURES, Ranker

# Settings tried when fitting, chosen by 3-fold cross-validation on the picks. Wider length scales
# make the score smoother (closer to Bradley-Terry); a bigger amplitude trusts the picks more.
LENGTH_SCALES = (0.5, 1.0, 2.0, 4.0)
AMPLITUDES = (0.5, 2.0, 8.0)
CV_FOLDS = 3
NEWTON_STEPS = 30


def _rbf(a: np.ndarray, b: np.ndarray, length_scale: float, amplitude: float) -> np.ndarray:
    sq = ((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)
    return amplitude * np.exp(-sq / (2 * length_scale ** 2))


class _Fit:
    """One Laplace-approximated GP over pairs (rows of first photo, second photo, P(first wins))."""

    def __init__(self, first, second, y, length_scale, amplitude):
        self.first, self.second, self.ls, self.amp = first, second, length_scale, amplitude
        k = lambda a, b: _rbf(a, b, length_scale, amplitude)
        K = k(first, first) + k(second, second) - k(first, second) - k(second, first)
        K += 1e-6 * np.eye(len(K))
        f = np.zeros(len(y))
        for _ in range(NEWTON_STEPS):
            pi = 1 / (1 + np.exp(-f))
            W = pi * (1 - pi)
            sw = np.sqrt(W)
            L = np.linalg.cholesky(np.eye(len(y)) + sw[:, None] * K * sw[None, :])
            b = W * f + (y - pi)
            a = b - sw * np.linalg.solve(L.T, np.linalg.solve(L, sw * (K @ b)))
            f_new = K @ a
            if np.max(np.abs(f_new - f)) < 1e-6:
                f = f_new
                break
            f = f_new
        pi = 1 / (1 + np.exp(-f))
        # The latent score of a photo is g(x) = sum_i c_i (k(x, first_i) - k(x, second_i)).
        self.c = y - pi
        self.sw = np.sqrt(pi * (1 - pi))
        self.L = np.linalg.cholesky(np.eye(len(y)) + self.sw[:, None] * K * self.sw[None, :])

    def _cross(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        k = lambda u, v: _rbf(u, v, self.ls, self.amp)
        return k(a, self.first) + k(b, self.second) - k(a, self.second) - k(b, self.first)

    def score(self, x: np.ndarray) -> np.ndarray:
        """Latent scores of photos (rows), on a scale where a difference of 1 is like BT's."""
        k = lambda u, v: _rbf(u, v, self.ls, self.amp)
        return (k(x, self.first) - k(x, self.second)) @ self.c

    def win_probability(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """P(a beats b) for rows of a and b, allowing for how unsure the GP is about the pair."""
        Ks = self._cross(a, b)
        mean = Ks @ self.c
        v = np.linalg.solve(self.L, self.sw[:, None] * Ks.T)
        prior = 2 * self.amp * (1 - np.exp(-((a - b) ** 2).sum(-1) / (2 * self.ls ** 2)))
        var = np.maximum(prior - (v ** 2).sum(0), 1e-9)
        # Probit approximation to averaging the logistic over the latent's uncertainty.
        return 1 / (1 + np.exp(-mean / np.sqrt(1 + np.pi * var / 8)))


class GPRanker:
    """Like ranker.Ranker: fit on (winner, loser) picks and (a, b) ties, then score photos."""

    def __init__(self, features: dict[str, dict[str, Optional[float]]]):
        # Standardised the same way as Bradley-Terry, so the two see exactly the same inputs.
        self._bt = Ranker(features)
        self.x = {photo: self._bt.x[i] for i, photo in enumerate(self._bt.photos)}
        self.fit_ = None
        self.length_scale = self.amplitude = None

    def vector(self, features: dict[str, Optional[float]]) -> np.ndarray:
        """A new photo's features, standardised like the training photos; missing counts as average."""
        bt = self._bt
        x = np.array([bt.mean[i] if features.get(name) is None else features[name]
                      for i, name in enumerate(FEATURES)], dtype=float)
        return np.nan_to_num((x - bt.mean) / bt.std)

    def _rows(self, choices, ties):
        known = [(w, l) for w, l in choices if w in self.x and l in self.x]
        tied = [(a, b) for a, b in ties if a in self.x and b in self.x]
        # Each pick both ways round, and a tie as half a win each way, as Bradley-Terry does.
        pairs = known + [(l, w) for w, l in known] + tied + [(b, a) for a, b in tied]
        y = np.r_[np.ones(len(known)), np.zeros(len(known)), np.full(2 * len(tied), 0.5)]
        first = np.array([self.x[a] for a, _ in pairs]).reshape(-1, len(FEATURES))
        second = np.array([self.x[b] for _, b in pairs]).reshape(-1, len(FEATURES))
        return first, second, y

    def _cv_score(self, choices, ties, ls, amp, seed=0) -> float:
        order = list(range(len(choices)))
        random.Random(seed).shuffle(order)
        right = total = 0
        for fold in range(CV_FOLDS):
            test = [choices[i] for j, i in enumerate(order) if j % CV_FOLDS == fold]
            train = [choices[i] for j, i in enumerate(order) if j % CV_FOLDS != fold]
            if not test or not train:
                continue
            fit = _Fit(*self._rows(train, ties), ls, amp)
            a = np.array([self.x[w] for w, _ in test])
            b = np.array([self.x[l] for _, l in test])
            right += int((fit.win_probability(a, b) > 0.5).sum())
            total += len(test)
        return right / total if total else 0.0

    def fit(self, choices: list[tuple[str, str]], ties: list[tuple[str, str]] = ()) -> None:
        choices = [(w, l) for w, l in choices if w in self.x and l in self.x]
        ties = list(ties)
        if not choices:
            self.fit_ = None
            return
        if len(choices) >= 2 * CV_FOLDS:
            scores = {(ls, amp): self._cv_score(choices, ties, ls, amp)
                      for ls in LENGTH_SCALES for amp in AMPLITUDES}
            # Ties in the CV score go to the smoother, more cautious setting.
            self.length_scale, self.amplitude = max(scores, key=lambda s: (scores[s], s[0], -s[1]))
        else:
            self.length_scale, self.amplitude = 2.0, 2.0
        self.fit_ = _Fit(*self._rows(choices, ties), self.length_scale, self.amplitude)

    def score_new(self, features: dict[str, Optional[float]]) -> float:
        """A photo's latent score; higher is liked more. 0 before fitting."""
        return float(self.fit_.score(self.vector(features)[None, :])[0]) if self.fit_ else 0.0

    def win_probability_new(self, a: dict, b: dict) -> float:
        """P(photo with features a is picked over photo with features b)."""
        if not self.fit_:
            return 0.5
        return float(self.fit_.win_probability(self.vector(a)[None, :], self.vector(b)[None, :])[0])
