async function loadSemanticMap() {
  const state = {
    data: null,
    currentSelection: null,
    expandedGroups: new Set(["root"]),
    search: "",
  };

  const elements = {
    loading: document.getElementById("loading"),
    error: document.getElementById("error"),
    tree: document.getElementById("tree"),
    content: document.getElementById("content"),
    stats: document.getElementById("stats"),
    headerMeta: document.getElementById("header-meta"),
    search: document.getElementById("search"),
  };

  try {
    const response = await fetch("coda_semantic_map_data.json");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    state.data = await response.json();
    initializeState(state);
    bindEvents(state, elements);
    renderAll(state, elements);
  } catch (error) {
    console.error(error);
    elements.loading.style.display = "none";
    elements.error.style.display = "block";
    elements.error.textContent = `Failed to load coda_semantic_map_data.json: ${error.message}`;
  }
}

function initializeState(state) {
  const firstVariable = state.data.variables[0];
  state.currentSelection = firstVariable ? { type: "variable", id: firstVariable.name } : { type: "root", id: "root" };
  collectGroupIds(state.data.tree, state.expandedGroups);
}

function collectGroupIds(node, expandedGroups) {
  if (node.type === "group" || node.type === "root") {
    expandedGroups.add(node.id);
  }

  (node.children || []).forEach((child) => {
    if (child.type === "group") {
      collectGroupIds(child, expandedGroups);
    }
  });
}

function bindEvents(state, elements) {
  elements.search.addEventListener("input", (event) => {
    state.search = event.target.value.trim().toLowerCase();
    renderTree(state, elements);
  });
}

function renderAll(state, elements) {
  elements.loading.style.display = "none";
  elements.error.style.display = "none";

  const stats = state.data.stats;
  elements.headerMeta.textContent = `${stats.variableCount} variables · ${stats.groupCount} groups · ${stats.valueMappingCount} mapped values`;
  elements.stats.innerHTML = [
    `<strong>Variables:</strong> ${stats.variableCount}`,
    `<strong>Groups:</strong> ${stats.groupCount}`,
    `<strong>Mapped variables:</strong> ${stats.mappedVariableCount}`,
    `<strong>Mapped values:</strong> ${stats.valueMappingCount}`,
  ].join("<br>");

  renderTree(state, elements);
  renderContent(state, elements);
}

function renderTree(state, elements) {
  elements.tree.innerHTML = "";
  const filteredTree = filterTree(state.data.tree, state);

  if (!filteredTree || !filteredTree.children || filteredTree.children.length === 0) {
    elements.tree.innerHTML = '<div class="empty-state">No matching schema nodes.</div>';
    return;
  }

  elements.tree.appendChild(renderTreeNode(filteredTree, state, elements, 0));
}

function filterTree(node, state) {
  if (!state.search) {
    return node;
  }

  const search = state.search;
  const labelMatches = node.label.toLowerCase().includes(search);

  if (node.type === "variable") {
    const variable = getVariableById(state.data, node.variableId);
    const haystacks = [
      node.label,
      variable?.description || "",
      variable?.section || "",
      ...(variable?.valueMapping || []).map((term) => `${term.label} ${term.targetClass || ""}`),
    ].join(" ").toLowerCase();

    return haystacks.includes(search) ? node : null;
  }

  const children = (node.children || [])
    .map((child) => filterTree(child, state))
    .filter(Boolean);

  if (labelMatches || children.length > 0 || node.id === "root") {
    return { ...node, children };
  }

  return null;
}

function renderTreeNode(node, state, elements, depth) {
  const container = document.createElement("div");

  if (node.id !== "root") {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `tree-row ${isSelected(state, node) ? "active" : ""}`;
    row.style.paddingLeft = `${depth * 16 + 12}px`;

    const count = node.type === "group"
      ? ` (${countVariables(node)})`
      : "";

    row.innerHTML = `
      <span class="tree-row-main">
        ${node.type === "group" ? `<span class="chevron">${state.expandedGroups.has(node.id) ? "▾" : "▸"}</span>` : `<span class="chevron chevron-placeholder">•</span>`}
        <span class="tree-label">${escapeHtml(node.label)}</span>
      </span>
      <span class="tree-type">${node.type === "group" ? `Group${count}` : "Variable"}</span>
    `;

    row.addEventListener("click", () => {
      if (node.type === "group") {
        if (state.expandedGroups.has(node.id)) {
          state.expandedGroups.delete(node.id);
        } else {
          state.expandedGroups.add(node.id);
        }
      }

      state.currentSelection = {
        type: node.type === "variable" ? "variable" : "group",
        id: node.type === "variable" ? node.variableId : node.id,
      };

      renderTree(state, elements);
      renderContent(state, elements);
    });

    container.appendChild(row);
  }

  if (node.type === "root" || (node.type === "group" && state.expandedGroups.has(node.id))) {
    (node.children || []).forEach((child) => {
      container.appendChild(renderTreeNode(child, state, elements, node.id === "root" ? depth : depth + 1));
    });
  }

  return container;
}

function renderContent(state, elements) {
  elements.content.innerHTML = "";

  if (state.currentSelection.type === "group") {
    const group = findGroupById(state.data.tree, state.currentSelection.id);
    if (group) {
      elements.content.appendChild(renderGroupCard(group));
    }
    return;
  }

  const variable = getVariableById(state.data, state.currentSelection.id);
  if (!variable) {
    elements.content.innerHTML = '<div class="card"><h2>Nothing selected</h2></div>';
    return;
  }

  elements.content.appendChild(renderVariableHeader(variable));
  elements.content.appendChild(renderSchemaReconstruction(variable));
  if (variable.valueMapping.length > 0) {
    elements.content.appendChild(renderValueMappings(variable));
  }
}

function renderGroupCard(group) {
  const card = document.createElement("div");
  card.className = "card";

  const variableCount = countVariables(group);
  const childGroups = (group.children || []).filter((child) => child.type === "group").length;

  card.innerHTML = `
    <div class="breadcrumbs">${group.path.map(escapeHtml).join(" / ")}</div>
    <h2>${escapeHtml(group.label)}</h2>
    <p class="muted">AYA-style schema group view generated from <code>coda_schema.jsonld</code>.</p>
    <div class="badge-row">
      <span class="badge"><strong>Variables:</strong> ${variableCount}</span>
      <span class="badge"><strong>Child groups:</strong> ${childGroups}</span>
    </div>
  `;

  return card;
}

function renderVariableHeader(variable) {
  const card = document.createElement("div");
  card.className = "card";

  const badges = [
    badge("Type", variable.type || "—"),
    badge("Data type", variable.dataType || "—"),
    badge("Class", variable.classId || "—"),
    badge("Predicate", variable.predicate || "—"),
    badge("Field type", variable.fieldType || "—"),
    badge("SQL type", variable.sqlType || "—"),
  ].join("");

  card.innerHTML = `
    <div class="breadcrumbs">${variable.path.map(escapeHtml).join(" / ")}</div>
    <h2>${escapeHtml(variable.name)}</h2>
    <p>${escapeHtml(variable.description || "No description available.")}</p>
    <div class="badge-row">${badges}</div>
  `;

  return card;
}

function renderSchemaReconstruction(variable) {
  const card = document.createElement("div");
  card.className = "card";
  const items = variable.schemaReconstruction
    .map((node) => `
      <li>
        <strong>${escapeHtml(node.aestheticLabel || node.classLabel || node.classId || "Class Node")}</strong>
        <div class="muted small">${escapeHtml(node.classId || "")}</div>
        <div class="muted small">Predicate: ${escapeHtml(node.predicate || "—")}</div>
      </li>
    `)
    .join("");

  card.innerHTML = `
    <h3>Schema Reconstruction</h3>
    ${items ? `<ul class="detail-list">${items}</ul>` : '<p class="muted">No reconstruction nodes available.</p>'}
  `;

  return card;
}

function renderValueMappings(variable) {
  const card = document.createElement("div");
  card.className = "card";

  const rows = variable.valueMapping
    .map((term) => `
      <tr>
        <td>${escapeHtml(term.label)}</td>
        <td><code>${escapeHtml(term.targetClass || "—")}</code></td>
      </tr>
    `)
    .join("");

  card.innerHTML = `
    <h3>Value Mapping</h3>
    <table>
      <thead>
        <tr>
          <th>Local value</th>
          <th>Target class</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  return card;
}

function badge(label, value) {
  return `<span class="badge"><strong>${escapeHtml(label)}:</strong> <code>${escapeHtml(value)}</code></span>`;
}

function countVariables(node) {
  if (node.type === "variable") {
    return 1;
  }
  return (node.children || []).reduce((count, child) => count + countVariables(child), 0);
}

function findGroupById(node, id) {
  if (node.id === id) {
    return node;
  }
  for (const child of node.children || []) {
    if (child.type === "group") {
      const found = findGroupById(child, id);
      if (found) {
        return found;
      }
    }
  }
  return null;
}

function getVariableById(data, variableId) {
  return data.variables.find((variable) => variable.name === variableId);
}

function isSelected(state, node) {
  return state.currentSelection.type === (node.type === "variable" ? "variable" : "group")
    && state.currentSelection.id === (node.type === "variable" ? node.variableId : node.id);
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

document.addEventListener("DOMContentLoaded", loadSemanticMap);