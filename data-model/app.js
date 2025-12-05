async function loadSemanticMap() {
  const loadingEl = document.getElementById("loading");
  const errorEl = document.getElementById("error");
  const groupsEl = document.getElementById("groups");
  const contentEl = document.getElementById("content");
  const headerMetaEl = document.getElementById("header-meta");

  try {
    const res = await fetch("data_semantic_map.json");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();

    loadingEl.style.display = "none";
    errorEl.style.display = "none";

    const variableInfo = data.variable_info || {};
    const grouped = groupVariablesByAestheticLabel(variableInfo);

    // Header metadata
    headerMetaEl.textContent = `${data.database_name || ""} · ${
      Object.keys(variableInfo).length
    } variables`;

    // Build sidebar
    renderSidebar(grouped, variableInfo, groupsEl, contentEl);

  } catch (err) {
    console.error(err);
    loadingEl.style.display = "none";
    errorEl.style.display = "block";
    errorEl.textContent = "Failed to load data_semantic_map.json: " + err.message;
  }
}

/**
 * Group variables by schema_reconstruction[].aesthetic_label.
 * Returns a map: { groupLabel: [varName, ...] }
 */
function groupVariablesByAestheticLabel(variableInfo) {
  const groups = {};

  for (const [varName, v] of Object.entries(variableInfo)) {
    const sr = v.schema_reconstruction || [];
    let label = "Other";

    if (sr.length > 0 && sr[0].aesthetic_label) {
      label = sr[0].aesthetic_label;
    }

    if (!groups[label]) groups[label] = [];
    groups[label].push(varName);
  }

  // sort variables within each group
  for (const g of Object.keys(groups)) {
    groups[g].sort();
  }

  return groups;
}

/**
 * Build sidebar UI and attach click handlers.
 */
function renderSidebar(grouped, variableInfo, groupsEl, contentEl) {
  groupsEl.innerHTML = "";
  const allGroupNames = Object.keys(grouped).sort();
  let firstVarName = null;

  allGroupNames.forEach((groupName) => {
    const groupDiv = document.createElement("div");
    groupDiv.className = "group";

    const title = document.createElement("div");
    title.className = "group-title";
    title.textContent = groupName;
    groupDiv.appendChild(title);

    const ul = document.createElement("ul");
    ul.className = "var-list";

    grouped[groupName].forEach((varName) => {
      const v = variableInfo[varName];
      const li = document.createElement("li");
      li.className = "var-item";
      li.dataset.varName = varName;

      const nameDiv = document.createElement("div");
      nameDiv.className = "var-name";
      nameDiv.textContent = varName;

      const labelDiv = document.createElement("div");
      labelDiv.className = "var-label";
      // show ontology class label if present, else NCIt code
      const cls = v.class || "";
      labelDiv.textContent = cls ? `Class: ${cls}` : "";

      li.appendChild(nameDiv);
      if (labelDiv.textContent) li.appendChild(labelDiv);

      li.addEventListener("click", () => {
        setActiveSidebarItem(varName);
        renderVariableDetail(varName, v, contentEl);
      });

      ul.appendChild(li);
      if (!firstVarName) firstVarName = varName;
    });

    groupDiv.appendChild(ul);
    groupsEl.appendChild(groupDiv);
  });

  // Auto-select first variable for convenience
  if (firstVarName) {
    setActiveSidebarItem(firstVarName);
    renderVariableDetail(firstVarName, variableInfo[firstVarName], contentEl);
  }
}

/**
 * Highlight the active variable in the sidebar.
 */
function setActiveSidebarItem(varName) {
  document.querySelectorAll(".var-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.varName === varName);
  });
}

/**
 * Render details of a single variable into the main content panel.
 */
function renderVariableDetail(varName, v, contentEl) {
  contentEl.innerHTML = "";

  const mainCard = document.createElement("div");
  mainCard.className = "card";

  const h2 = document.createElement("h2");
  h2.textContent = varName;
  mainCard.appendChild(h2);

  const metaDiv = document.createElement("div");
  metaDiv.className = "muted";

  const predicateBadge = makeBadge("Predicate", v.predicate || "—");
  const classBadge = makeBadge("Class", v.class || "—");
  metaDiv.appendChild(predicateBadge);
  metaDiv.appendChild(classBadge);

  mainCard.appendChild(metaDiv);

  if (v.local_definition) {
    const p = document.createElement("p");
    p.style.marginTop = "0.75rem";
    p.textContent = v.local_definition;
    mainCard.appendChild(p);
  }

  contentEl.appendChild(mainCard);

  // Schema reconstruction block
  if (Array.isArray(v.schema_reconstruction) && v.schema_reconstruction.length > 0) {
    const srCard = document.createElement("div");
    srCard.className = "card";

    const h3 = document.createElement("h3");
    h3.textContent = "Schema reconstruction";
    srCard.appendChild(h3);

    const list = document.createElement("ul");
    list.style.paddingLeft = "1.2rem";

    v.schema_reconstruction.forEach((item) => {
      const li = document.createElement("li");
      const label = item.class_label || item.class || "Group";
      const predicate = item.predicate || "";
      const aesthetic = item.aesthetic_label || "";

      li.innerHTML = `
        <strong>${escapeHtml(label)}</strong>
        ${aesthetic ? `<span class="pill">${escapeHtml(aesthetic)}</span>` : ""}
        ${predicate ? `<br/><span class="muted">via ${escapeHtml(predicate)}</span>` : ""}
      `;
      list.appendChild(li);
    });

    srCard.appendChild(list);
    contentEl.appendChild(srCard);
  }

  // Value mapping block
  if (v.value_mapping && v.value_mapping.terms) {
    const vmCard = document.createElement("div");
    vmCard.className = "card";

    const h3 = document.createElement("h3");
    h3.textContent = "Value mappings";
    vmCard.appendChild(h3);

    const table = document.createElement("table");
    const thead = document.createElement("thead");
    thead.innerHTML = `
      <tr>
        <th>Local value</th>
        <th>Ontology class</th>
      </tr>
    `;
    table.appendChild(thead);

    const tbody = document.createElement("tbody");

    Object.entries(v.value_mapping.terms).forEach(([localVal, cfg]) => {
      const tr = document.createElement("tr");
      const localTd = document.createElement("td");
      const classTd = document.createElement("td");

      localTd.textContent = localVal;

      const target = cfg && cfg.target_class ? cfg.target_class : "—";
      classTd.innerHTML = `<code>${escapeHtml(target)}</code>`;

      tr.appendChild(localTd);
      tr.appendChild(classTd);
      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    vmCard.appendChild(table);
    contentEl.appendChild(vmCard);
  }
}

/**
 * Utility: create a metadata badge.
 */
function makeBadge(label, value) {
  const span = document.createElement("span");
  span.className = "badge";
  span.innerHTML = `<strong>${escapeHtml(label)}:</strong> <code>${escapeHtml(
    value
  )}</code>`;
  return span;
}

/**
 * Simple HTML escaping helper.
 */
function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.addEventListener("DOMContentLoaded", loadSemanticMap);
