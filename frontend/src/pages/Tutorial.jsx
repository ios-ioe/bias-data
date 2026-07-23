import { useMemo, useState } from "react";
import { useTeam } from "../context/TeamContext.jsx";
import { CATEGORIES } from "../config/quotas.js";
import tutorialData from "../data/tutorialData.json";
import Badge from "../components/Badge.jsx";
import ProgressCard from "../components/ProgressCard.jsx";
import EmptyState from "../components/EmptyState.jsx";
import TopBar from "../components/TopBar.jsx";

const ITEMS = tutorialData.items || [];

const emptyAnswers = () =>
  CATEGORIES.reduce((acc, category) => ({ ...acc, [category.key]: 0 }), {});

export default function Tutorial() {
  const { team_name, logout } = useTeam();

  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState(emptyAnswers);
  const [responses, setResponses] = useState([]); // per-item { itemId, answers }
  const [finished, setFinished] = useState(false);

  const current = ITEMS[index] || null;
  const total = ITEMS.length;

  const anyBias = useMemo(
    () => CATEGORIES.some((category) => answers[category.key] === 1),
    [answers]
  );

  function setAnswer(key, value) {
    setAnswers((prev) => ({ ...prev, [key]: value }));
  }

  function handleNext() {
    if (!current) return;
    const updatedResponses = [...responses, { itemId: current.id, answers }];
    setResponses(updatedResponses);
    setAnswers(emptyAnswers());

    if (index + 1 >= total) {
      setFinished(true);
    } else {
      setIndex((i) => i + 1);
    }
  }

  function handleRestart() {
    setIndex(0);
    setAnswers(emptyAnswers());
    setResponses([]);
    setFinished(false);
  }

  // Score the completed attempt against the reference labels in the JSON file.
  const score = useMemo(() => {
    if (!finished) return null;

    let correctCells = 0;
    let totalCells = 0;
    let perfectItems = 0;

    const perCategory = CATEGORIES.reduce(
      (acc, category) => ({ ...acc, [category.key]: { correct: 0, total: 0 } }),
      {}
    );

    const itemResults = responses.map((response) => {
      const item = ITEMS.find((i) => i.id === response.itemId);
      const reference = item?.labels || {};
      let itemCorrect = true;
      const cellResults = CATEGORIES.map((category) => {
        const given = response.answers[category.key];
        const expected = Number(reference[category.key]) === 1 ? 1 : 0;
        const isRight = given === expected;

        totalCells += 1;
        perCategory[category.key].total += 1;
        if (isRight) {
          correctCells += 1;
          perCategory[category.key].correct += 1;
        } else {
          itemCorrect = false;
        }

        return { key: category.key, label: category.label, given, expected, isRight };
      });

      if (itemCorrect) perfectItems += 1;

      return {
        item,
        cellResults,
        itemCorrect,
      };
    });

    return {
      itemResults,
      correctCells,
      totalCells,
      perfectItems,
      perCategory,
      pct: totalCells === 0 ? 0 : Math.round((correctCells / totalCells) * 100),
    };
  }, [finished, responses]);

  if (total === 0) {
    return (
      <div className="submit">
        <TopBar
          label={team_name}
          links={[
            { to: "/submit", text: "Submit" },
            { to: "/dashboard", text: "Dashboard" },
            { to: "/tutorial", text: "Tutorial" },
          ]}
          onSignOut={logout}
        />
        <EmptyState
          title="No tutorial data"
          message="The tutorial dataset is empty. Ask an organizer to add sample sentences to tutorialData.json."
        />
      </div>
    );
  }

  return (
    <div className="submit">
      <TopBar
        label={team_name}
        links={[
          { to: "/submit", text: "Submit" },
          { to: "/dashboard", text: "Dashboard" },
          { to: "/tutorial", text: "Tutorial" },
        ]}
        onSignOut={logout}
      />

      <div className="submit-head">
        <div>
          <h1 className="page-title">Bias tutorial</h1>
          <p className="page-sub">{tutorialData.instructions}</p>
        </div>
        {!finished && (
          <div className="stat-pill">
            <span className="stat-num">
              {index + 1} / {total}
            </span>
            <span className="stat-cap">sentence</span>
          </div>
        )}
      </div>

      {!finished && current && (
        <>
          <div className="submit-grid">
            <section className="panel">
              <span className="field-label">Sentence {index + 1} of {total}</span>
              <p className="nepali" style={{ fontSize: 18, marginTop: 12 }}>
                {current.text}
              </p>
            </section>

            <section className="panel">
              <div className="labels-head">
                <span className="field-label">Bias categories</span>
                <Badge variant={anyBias ? "accent" : "neutral"}>
                  {anyBias ? "biased" : "non-biased"}
                </Badge>
              </div>
              <div className="labels">
                {CATEGORIES.map((category) => (
                  <div className="label-row" key={category.key}>
                    <span className="label-name">{category.label}</span>
                    <fieldset className="radio-group">
                      <legend className="sr-only">{category.label}</legend>
                      <label className="radio-label">
                        <input
                          type="radio"
                          name={category.key}
                          value="0"
                          checked={answers[category.key] === 0}
                          onChange={() => setAnswer(category.key, 0)}
                        />
                        <span>No</span>
                      </label>
                      <label className="radio-label">
                        <input
                          type="radio"
                          name={category.key}
                          value="1"
                          checked={answers[category.key] === 1}
                          onChange={() => setAnswer(category.key, 1)}
                        />
                        <span>Yes</span>
                      </label>
                    </fieldset>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <div className="submit-bar">
            <button type="button" className="btn btn-primary btn-lg" onClick={handleNext}>
              {index + 1 >= total ? "Finish & see results" : "Next sentence"}
            </button>
          </div>
        </>
      )}

      {finished && score && (
        <>
          <div className="dash-summary">
            <ProgressCard
              label="Overall accuracy"
              value={`${score.pct}%`}
              hint={`${score.correctCells} / ${score.totalCells} labels correct`}
              accent
            />
            <ProgressCard
              label="Perfect sentences"
              value={score.perfectItems}
              hint={`of ${total} sentences`}
            />
            <ProgressCard label="Sentences reviewed" value={total} />
          </div>

          <section className="panel quota-panel">
            <h2 className="section-title">Accuracy by category</h2>
            <div className="quota-grid">
              {CATEGORIES.map((category) => {
                const stat = score.perCategory[category.key];
                const pct = stat.total === 0 ? 0 : Math.round((stat.correct / stat.total) * 100);
                return (
                  <div className="label-row" key={category.key}>
                    <span className="label-name">{category.label}</span>
                    <span>
                      {stat.correct} / {stat.total} ({pct}%)
                    </span>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="panel">
            <h2 className="section-title">Answer review</h2>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Text</th>
                    <th>Result</th>
                    <th>Mismatched categories</th>
                  </tr>
                </thead>
                <tbody>
                  {score.itemResults.map((result, i) => {
                    const wrong = result.cellResults.filter((c) => !c.isRight);
                    return (
                      <tr key={result.item?.id ?? i} className={!result.itemCorrect ? "row-flagged" : ""}>
                        <td className="td-text nepali">{result.item?.text}</td>
                        <td>
                          <Badge variant={result.itemCorrect ? "success" : "accent"}>
                            {result.itemCorrect ? "correct" : "needs review"}
                          </Badge>
                        </td>
                        <td className="td-labels">
                          {wrong.length === 0 && <span>—</span>}
                          {wrong.map((c) => (
                            <Badge key={c.key} variant="neutral">
                              {c.label}: you said {c.given ? "yes" : "no"}, answer is{" "}
                              {c.expected ? "yes" : "no"}
                            </Badge>
                          ))}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <div className="submit-bar">
            <button type="button" className="btn btn-primary btn-lg" onClick={handleRestart}>
              Try again
            </button>
          </div>
        </>
      )}
    </div>
  );
}
