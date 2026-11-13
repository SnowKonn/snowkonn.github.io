(() => {
  const rows = [...document.querySelectorAll(".ledger > li")];
  const years = [...document.querySelectorAll(".year")];
  const count = document.querySelector(".count");
  const empty = document.querySelector(".empty");
  const search = document.querySelector("#q");
  const state = { house: "all", topic: "all", q: "" };

  function apply() {
    let shown = 0;
    for (const li of rows) {
      const ok =
        (state.house === "all" || li.dataset.house === state.house) &&
        (state.topic === "all" || li.dataset.topics.split(" ").includes(state.topic)) &&
        (!state.q || li.dataset.text.includes(state.q));
      li.hidden = !ok;
      shown += ok;
    }
    for (const y of years) y.hidden = !y.querySelector(".ledger > li:not([hidden])");
    if (count) count.textContent = count.dataset.tpl.replace("{n}", shown);
    if (empty) empty.hidden = shown > 0;
  }

  for (const group of document.querySelectorAll(".chips")) {
    group.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      state[group.dataset.key] = b.dataset.value;
      for (const x of group.querySelectorAll("button")) x.setAttribute("aria-pressed", x === b);
      apply();
    });
  }
  if (search) search.addEventListener("input", () => { state.q = search.value.trim().toLowerCase(); apply(); });

  // Tape: show the report under the pointer in the caption line.
  const now = document.querySelector(".tape-caption .now");
  if (now) {
    const rest = now.textContent;
    for (const t of document.querySelectorAll(".tape .tick")) {
      const show = () => { now.textContent = t.dataset.label; };
      const hide = () => { now.textContent = rest; };
      t.addEventListener("mouseenter", show);
      t.addEventListener("focus", show);
      t.addEventListener("mouseleave", hide);
      t.addEventListener("blur", hide);
      t.addEventListener("click", () => {
        // A filtered-out row cannot be scrolled to: clear filters first.
        const target = document.querySelector(t.getAttribute("href"));
        if (target && target.hidden) {
          state.house = state.topic = "all"; state.q = ""; if (search) search.value = "";
          for (const b of document.querySelectorAll(".chips button")) b.setAttribute("aria-pressed", b.dataset.value === "all");
          apply();
        }
      });
    }
  }
})();
