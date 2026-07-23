// Category keys MUST match the dataset column names exactly (typos included) —
// this data merges into the published dataset later. `label` is display-only.
export const CATEGORIES = [
  { key: "gender", label: "Gender" },
  { key: "caste", label: "Caste" },
  { key: "religional", label: "Regional" },
  { key: "religion", label: "Religion" },
  { key: "appearence", label: "Appearance" },
  { key: "socialstatus", label: "Social status" },
  { key: "Age", label: "Age" },
  { key: "Disablity", label: "Disability" },
  { key: "political", label: "Political" },
  { key: "amiguity", label: "Ambiguity" },
];

// Sums to exactly 160 -- the minimum a team must submit (spread across
// these 10 categories) to hit 100% completion. No cap after that: teams
// can keep submitting past 160, it just doesn't add further quota %.
export const QUOTAS = {
  gender: 20,
  caste: 16,
  religional: 16,
  religion: 14,
  appearence: 14,
  socialstatus: 14,
  Age: 15,
  Disablity: 15,
  political: 16,
  amiguity: 20,
};

export const SOURCE_PLATFORMS = [
  "Facebook",
  "YouTube",
  "TikTok",
  "X / Twitter",
  "Instagram",
  "News comments",
  "Reddit",
  "Other",
];

// Given a team's rows, compute per-category counts.
export function countByCategory(rows) {
  const counts = {};
  CATEGORIES.forEach((c) => (counts[c.key] = 0));
  for (const r of rows) {
    for (const c of CATEGORIES) {
      if (Number(r[c.key]) === 1) {
        counts[c.key] += 1;
      }
    }
  }
  return { counts };
}

// Overall completion % for a team (capped per category).
export function completionPct(rows) {
  const { counts } = countByCategory(rows);
  let got = 0;
  let need = 0;
  for (const c of CATEGORIES) {
    need += QUOTAS[c.key];
    got += Math.min(counts[c.key], QUOTAS[c.key]);
  }
  return need === 0 ? 0 : Math.round((got / need) * 100);
}

export function totalQuotaUnits() {
  return CATEGORIES.reduce((sum, category) => sum + QUOTAS[category.key], 0);
}

export function quotaProgress(rows) {
  const { counts } = countByCategory(rows);
  let earned = 0;
  const need = totalQuotaUnits();

  for (const category of CATEGORIES) {
    earned += Math.min(counts[category.key], QUOTAS[category.key]);
  }

  const completedCategories = CATEGORIES.filter(
    (category) => counts[category.key] >= QUOTAS[category.key]
  ).map((category) => category.label);

  return {
    earned,
    need,
    remaining: Math.max(0, need - earned),
    completedCategories,
    pct: need === 0 ? 0 : Math.round((earned / need) * 100),
  };
}
