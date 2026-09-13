/* ==============================================================================
   COOKED - Recipe Box, Scaling & Interactive Cooking Mode
   ============================================================================== */

let currentRecipeScope = "all";
let activeRecipeDetail = null;
let currentServingsScale = 1.0;

async function loadRecipesView(scope = "all") {
  currentRecipeScope = scope;
  const container = document.getElementById("main-content-view");
  if (!container) return;

  container.innerHTML = `
    <div class="recipe-box-header">
      <div>
        <h2>Recipe Box</h2>
        <p style="color: var(--text-muted); font-size: 0.88rem;">Your personal culinary vault & discovery engine</p>
      </div>
      <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
        <button class="btn btn-secondary btn-sm" onclick="openScraperModal()">
          <span>🔗</span> Import from Web
        </button>
        <button class="btn btn-primary btn-sm" onclick="openRecipeEditorModal()">
          <span>+</span> Write Recipe
        </button>
      </div>
    </div>

    <!-- Search & Filter Controls -->
    <div style="display: flex; gap: 0.75rem; margin-bottom: 1.25rem; flex-wrap: wrap;">
      <div class="recipe-tabs">
        <button class="filter-chip ${scope === 'all' ? 'active' : ''}" onclick="loadRecipesView('all')">All Recipes</button>
        <button class="filter-chip ${scope === 'mine' ? 'active' : ''}" onclick="loadRecipesView('mine')">My Recipes</button>
        <button class="filter-chip ${scope === 'saved' ? 'active' : ''}" onclick="loadRecipesView('saved')">Saved Box</button>
      </div>
      <div style="margin-left: auto; display: flex; gap: 0.5rem;">
        <select id="recipe-cuisine-filter" class="form-control" style="width: auto; padding: 0.35rem 0.65rem; font-size: 0.82rem;" onchange="applyRecipeFilters()">
          <option value="All">All Cuisines</option>
          <option value="Italian">Italian</option>
          <option value="French / Artisan">French / Artisan</option>
          <option value="American">American</option>
          <option value="Mexican">Mexican</option>
          <option value="Asian">Asian</option>
          <option value="Mediterranean">Mediterranean</option>
        </select>
        <select id="recipe-difficulty-filter" class="form-control" style="width: auto; padding: 0.35rem 0.65rem; font-size: 0.82rem;" onchange="applyRecipeFilters()">
          <option value="All">All Difficulties</option>
          <option value="Easy">Easy</option>
          <option value="Medium">Medium</option>
          <option value="Advanced">Advanced</option>
        </select>
      </div>
    </div>

    <div id="recipe-grid-container" class="recipe-grid">
      <div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: var(--text-light);">
        Loading recipes...
      </div>
    </div>
  `;

  await fetchAndRenderRecipes();
}

async function fetchAndRenderRecipes(customQuery = "") {
  const cuisine = document.getElementById("recipe-cuisine-filter")?.value || "All";
  const difficulty = document.getElementById("recipe-difficulty-filter")?.value || "All";

  let url = `/api/recipes?scope=${encodeURIComponent(currentRecipeScope)}`;
  if (cuisine !== "All") url += `&cuisine=${encodeURIComponent(cuisine)}`;
  if (difficulty !== "All") url += `&difficulty=${encodeURIComponent(difficulty)}`;
  if (customQuery) url += `&q=${encodeURIComponent(customQuery)}`;

  try {
    const data = await apiRequest(url);
    const container = document.getElementById("recipe-grid-container");
    if (!container) return;

    if (!data.recipes || data.recipes.length === 0) {
      container.innerHTML = `
        <div style="grid-column: 1/-1; text-align: center; padding: 3rem 1rem; background: var(--bg-surface); border: 1px dashed var(--border-color); border-radius: var(--radius-lg);">
          <span style="font-size: 2.5rem; display: block; margin-bottom: 0.5rem;">📖</span>
          <h3>No recipes found</h3>
          <p style="color: var(--text-muted); font-size: 0.9rem; margin-top: 0.25rem;">
            ${currentRecipeScope === 'saved' ? 'Your saved recipe box is empty. Bookmark community recipes to see them here!' : 'Try adjusting your filters or create a new recipe!'}
          </p>
        </div>
      `;
      return;
    }

    container.innerHTML = data.recipes.map(recipe => renderRecipeCard(recipe)).join("");
  } catch (err) {
    showToast("Error loading recipes: " + err.message, "error");
  }
}

function applyRecipeFilters() {
  fetchAndRenderRecipes();
}

function renderRecipeCard(recipe) {
  const tags = (recipe.tags || []).slice(0, 3).map(t => `<span class="badge badge-secondary">#${escapeHtml(t)}</span>`).join(" ");
  const defaultImg = "https://images.unsplash.com/photo-1495521821757-a1efb6729352?w=600&auto=format&fit=crop&q=80";

  return `
    <div class="recipe-card" onclick="viewRecipeDetail(${recipe.id})">
      <img class="recipe-card-img" src="${escapeHtml(recipe.image_url || defaultImg)}" alt="${escapeHtml(recipe.title)}" />
      <div class="recipe-card-body">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.35rem;">
          <span class="badge badge-primary">${escapeHtml(recipe.cuisine || 'Global')}</span>
          <button class="btn-icon" style="padding: 2px;" onclick="event.stopPropagation(); toggleSaveRecipe(${recipe.id}, this)">
            ${recipe.is_saved ? '❤️' : '🤍'}
          </button>
        </div>
        <h3 class="recipe-card-title">${escapeHtml(recipe.title)}</h3>
        <p style="color: var(--text-muted); font-size: 0.82rem; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
          ${escapeHtml(recipe.description || '')}
        </p>
        <div class="recipe-card-tags">${tags}</div>
        <div class="recipe-card-meta">
          <span>⏱️ ${(recipe.prep_time_min || 0) + (recipe.cook_time_min || 0)}m</span>
          <span>📊 ${escapeHtml(recipe.difficulty || 'Medium')}</span>
          <span>🍽️ ${recipe.servings || 4} serv</span>
        </div>
      </div>
    </div>
  `;
}

async function viewRecipeDetail(recipeId) {
  try {
    const data = await apiRequest(`/api/recipes/${recipeId}`);
    activeRecipeDetail = data.recipe;
    currentServingsScale = 1.0;
    renderRecipeDetailView();
  } catch (err) {
    showToast("Error opening recipe: " + err.message, "error");
  }
}

function renderRecipeDetailView() {
  const r = activeRecipeDetail;
  if (!r) return;

  const container = document.getElementById("main-content-view");
  if (!container) return;

  const baseServings = r.servings || 4;
  const currentServings = Math.max(1, Math.round(baseServings * currentServingsScale));
  const isOwner = currentUser && (currentUser.id === r.user_id || currentUser.is_admin === 1);

  const tagsHtml = (r.tags || []).map(t => `<span class="badge badge-secondary">#${escapeHtml(t)}</span>`).join(" ");

  // Scale ingredients
  const ingredientsHtml = (r.ingredients || []).map((ing, idx) => {
    let scaledAmount = ing.amount || "";
    if (scaledAmount && !isNaN(parseFloat(scaledAmount))) {
      const val = parseFloat(scaledAmount) * currentServingsScale;
      scaledAmount = Number.isInteger(val) ? val.toString() : val.toFixed(1).replace(/\.0$/, "");
    }
    return `
      <div class="ingredient-item">
        <span><b>${escapeHtml(scaledAmount)} ${escapeHtml(ing.unit || '')}</b> ${escapeHtml(ing.name)}</span>
        <span class="badge badge-secondary" style="font-size: 0.7rem;">${escapeHtml(ing.category || 'Pantry')}</span>
      </div>
    `;
  }).join("");

  // Instructions step by step
  const stepsHtml = (r.steps || []).map((st, idx) => {
    return `
      <div class="instruction-step" id="step-row-${idx}">
        <div class="step-num">${st.step_number || (idx + 1)}</div>
        <div class="step-content">
          <label class="step-check">
            <input type="checkbox" onchange="toggleStepComplete(${idx}, this)" />
            <span class="step-instruction">${escapeHtml(st.instruction)}</span>
          </label>
        </div>
      </div>
    `;
  }).join("");

  container.innerHTML = `
    <div style="margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center;">
      <button class="btn btn-secondary btn-sm" onclick="loadRecipesView('${currentRecipeScope}')">
        ← Back to Recipe Box
      </button>
      <div style="display: flex; gap: 0.5rem;">
        <button class="btn btn-outline btn-sm" onclick="toggleSaveRecipe(${r.id})">
          ${r.is_saved ? '❤️ Saved to Box' : '🤍 Save to Box'}
        </button>
        <button class="btn btn-secondary btn-sm" onclick="forkRecipe(${r.id})">
          🍴 Fork Recipe
        </button>
        ${isOwner ? `
          <button class="btn btn-secondary btn-sm" onclick="openRecipeEditorModal(${r.id})">✏️ Edit</button>
          <button class="btn btn-danger btn-sm" onclick="deleteRecipe(${r.id})">🗑️ Delete</button>
        ` : ''}
      </div>
    </div>

    <!-- Recipe Hero Banner -->
    <div class="recipe-detail-header">
      ${r.image_url ? `
        <div style="cursor: pointer; position: relative;" onclick="openLightbox('${escapeHtml(r.image_url)}', '${escapeHtml(r.title)}')">
          <img class="recipe-hero-img" src="${escapeHtml(r.image_url)}" alt="${escapeHtml(r.title)}" />
          <span style="position: absolute; bottom: 12px; right: 12px; background: rgba(0,0,0,0.6); color: #fff; padding: 4px 10px; border-radius: var(--radius-full); font-size: 0.8rem;">🔍 Zoom Photo</span>
        </div>
      ` : ''}
      <div class="recipe-hero-content">
        <div style="display: flex; gap: 0.5rem; margin-bottom: 0.5rem;">
          <span class="badge badge-primary">${escapeHtml(r.cuisine || 'Global')}</span>
          <span class="badge badge-success">${escapeHtml(r.difficulty || 'Medium')}</span>
        </div>
        <h1 style="font-size: 1.8rem; margin-bottom: 0.5rem;">${escapeHtml(r.title)}</h1>
        <p style="color: var(--text-muted); font-size: 1rem; margin-bottom: 1rem;">${escapeHtml(r.description || '')}</p>
        
        <div style="display: flex; align-items: center; gap: 0.75rem;">
          <img src="${escapeHtml(r.author_avatar || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" />
          <div>
            <span style="font-weight: 700; font-size: 0.9rem; cursor: pointer;" onclick="openUserProfile('${escapeHtml(r.author_username)}')">
              Chef ${escapeHtml(r.author_display_name || r.author_username)}
            </span>
            ${r.orig_author_username ? `<span style="font-size: 0.78rem; color: var(--text-light); display: block;">Forked from @${escapeHtml(r.orig_author_username)}</span>` : ''}
          </div>
        </div>

        <div class="recipe-meta-badges">
          <div class="meta-badge-box">
            <div class="label">Prep Time</div>
            <div class="value">${r.prep_time_min || 0}m</div>
          </div>
          <div class="meta-badge-box">
            <div class="label">Cook Time</div>
            <div class="value">${r.cook_time_min || 0}m</div>
          </div>
          <div class="meta-badge-box">
            <div class="label">Total Time</div>
            <div class="value">${(r.prep_time_min || 0) + (r.cook_time_min || 0)}m</div>
          </div>
          <div class="meta-badge-box">
            <div class="label">Servings</div>
            <div class="value">${currentServings}</div>
          </div>
        </div>
        <div style="display: flex; gap: 0.35rem; flex-wrap: wrap;">${tagsHtml}</div>
      </div>
    </div>

    <!-- Interactive Cooking Columns -->
    <div class="recipe-interactive-grid">
      <!-- Ingredients Column with Multiplier -->
      <div class="ingredients-panel">
        <h3 style="margin-bottom: 0.75rem;">🛒 Ingredients</h3>
        
        <div class="servings-stepper">
          <span style="font-size: 0.85rem; font-weight: 600;">Scale Servings:</span>
          <div style="display: flex; align-items: center; gap: 0.4rem;">
            <button class="btn btn-secondary btn-sm" onclick="adjustServingsScale(-0.5)" ${currentServingsScale <= 0.5 ? 'disabled' : ''}>-</button>
            <span style="font-weight: 700; min-width: 32px; text-align: center;">${currentServings}</span>
            <button class="btn btn-secondary btn-sm" onclick="adjustServingsScale(0.5)">+</button>
          </div>
        </div>

        <div id="recipe-ingredients-list">
          ${ingredientsHtml}
        </div>
      </div>

      <!-- Instructions Column (Step-by-Step Cooking Checklist) -->
      <div class="instructions-panel">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
          <h3>👨‍🍳 Step-by-Step Directions</h3>
          <span style="font-size: 0.8rem; color: var(--text-muted);">Check steps as you cook!</span>
        </div>
        <div>
          ${stepsHtml}
        </div>
      </div>
    </div>
  `;
}

function adjustServingsScale(delta) {
  currentServingsScale = Math.max(0.5, currentServingsScale + delta);
  renderRecipeDetailView();
}

function toggleStepComplete(idx, checkbox) {
  const row = document.getElementById(`step-row-${idx}`);
  if (row) {
    if (checkbox.checked) {
      row.classList.add("step-completed");
    } else {
      row.classList.remove("step-completed");
    }
  }
}

async function toggleSaveRecipe(recipeId, btnEl) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }
  try {
    const isSaved = activeRecipeDetail?.is_saved || (btnEl && btnEl.textContent.includes('❤️'));
    const method = isSaved ? "DELETE" : "POST";
    const data = await apiRequest(`/api/recipes/${recipeId}/save`, { method });
    
    showToast(data.is_saved ? "Saved to your Recipe Box!" : "Removed from Recipe Box", "success");
    if (activeRecipeDetail && activeRecipeDetail.id === recipeId) {
      activeRecipeDetail.is_saved = data.is_saved;
      renderRecipeDetailView();
    } else {
      fetchAndRenderRecipes();
    }
  } catch (err) {
    showToast("Error updating saved status: " + err.message, "error");
  }
}

async function forkRecipe(recipeId) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }
  try {
    const data = await apiRequest(`/api/recipes/${recipeId}/fork`, { method: "POST" });
    showToast(data.message, "success");
    viewRecipeDetail(data.recipe_id);
  } catch (err) {
    showToast("Fork error: " + err.message, "error");
  }
}

async function deleteRecipe(recipeId) {
  if (!confirm("Are you sure you want to delete this recipe?")) return;
  try {
    await apiRequest(`/api/recipes/${recipeId}`, { method: "DELETE" });
    showToast("Recipe deleted successfully", "info");
    loadRecipesView(currentRecipeScope);
  } catch (err) {
    showToast("Error deleting recipe: " + err.message, "error");
  }
}

/* ==============================================================================
   RECIPE CREATION / EDITOR MODAL WIZARD
   ============================================================================== */

let editorIngredients = [];
let editorSteps = [];

function openRecipeEditorModal(recipeIdToEdit = null) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }

  const modal = document.getElementById("recipe-editor-modal");
  if (!modal) return;

  const isEdit = Boolean(recipeIdToEdit && activeRecipeDetail && activeRecipeDetail.id === recipeIdToEdit);
  const r = isEdit ? activeRecipeDetail : {
    id: null,
    title: "",
    description: "",
    prep_time_min: 15,
    cook_time_min: 25,
    servings: 4,
    difficulty: "Medium",
    cuisine: "Global",
    tags: ["HomeCooking"],
    image_url: "",
    ingredients: [
      { name: "Extra Virgin Olive Oil", amount: "2", unit: "tbsp", category: "Pantry" },
      { name: "Garlic Cloves (minced)", amount: "3", unit: "cloves", category: "Produce" }
    ],
    steps: [
      { step_number: 1, instruction: "Prep all ingredients and preheat cooking vessel." },
      { step_number: 2, instruction: "Combine and simmer until aromatic." }
    ]
  };

  editorIngredients = JSON.parse(JSON.stringify(r.ingredients || []));
  editorSteps = JSON.parse(JSON.stringify(r.steps || []));

  document.getElementById("editor-modal-title").textContent = isEdit ? "Edit Recipe" : "Create New Recipe";
  document.getElementById("editor-recipe-id").value = isEdit ? r.id : "";
  document.getElementById("editor-title").value = r.title || "";
  document.getElementById("editor-desc").value = r.description || "";
  document.getElementById("editor-prep").value = r.prep_time_min || 15;
  document.getElementById("editor-cook").value = r.cook_time_min || 25;
  document.getElementById("editor-servings").value = r.servings || 4;
  document.getElementById("editor-difficulty").value = r.difficulty || "Medium";
  document.getElementById("editor-cuisine").value = r.cuisine || "Global";
  document.getElementById("editor-tags").value = (r.tags || []).join(", ");
  document.getElementById("editor-image-url").value = r.image_url || "";

  renderEditorIngredients();
  renderEditorSteps();

  modal.classList.add("show");
}

function closeRecipeEditorModal() {
  const modal = document.getElementById("recipe-editor-modal");
  if (modal) modal.classList.remove("show");
}

function renderEditorIngredients() {
  const container = document.getElementById("editor-ingredients-list");
  if (!container) return;

  container.innerHTML = editorIngredients.map((ing, idx) => `
    <div style="display: grid; grid-template-columns: 80px 80px 1fr 110px 36px; gap: 0.4rem; align-items: center; margin-bottom: 0.4rem;">
      <input type="text" class="form-control" placeholder="Qty" value="${escapeHtml(ing.amount)}" onchange="editorIngredients[${idx}].amount = this.value" />
      <input type="text" class="form-control" placeholder="Unit" value="${escapeHtml(ing.unit)}" onchange="editorIngredients[${idx}].unit = this.value" />
      <input type="text" class="form-control" placeholder="Ingredient name" value="${escapeHtml(ing.name)}" onchange="editorIngredients[${idx}].name = this.value" />
      <select class="form-control" onchange="editorIngredients[${idx}].category = this.value">
        <option value="Produce" ${ing.category === 'Produce' ? 'selected' : ''}>Produce</option>
        <option value="Dairy" ${ing.category === 'Dairy' ? 'selected' : ''}>Dairy</option>
        <option value="Meat" ${ing.category === 'Meat' ? 'selected' : ''}>Meat</option>
        <option value="Pantry" ${ing.category === 'Pantry' ? 'selected' : ''}>Pantry</option>
        <option value="Spices" ${ing.category === 'Spices' ? 'selected' : ''}>Spices</option>
        <option value="Bakery" ${ing.category === 'Bakery' ? 'selected' : ''}>Bakery</option>
      </select>
      <button type="button" class="btn-icon" style="color: var(--danger);" onclick="removeEditorIngredient(${idx})">✕</button>
    </div>
  `).join("");
}

function addEditorIngredient() {
  editorIngredients.push({ name: "", amount: "", unit: "", category: "Pantry" });
  renderEditorIngredients();
}

function removeEditorIngredient(idx) {
  editorIngredients.splice(idx, 1);
  renderEditorIngredients();
}

function renderEditorSteps() {
  const container = document.getElementById("editor-steps-list");
  if (!container) return;

  container.innerHTML = editorSteps.map((st, idx) => `
    <div style="display: flex; gap: 0.5rem; align-items: flex-start; margin-bottom: 0.5rem;">
      <span class="step-num" style="margin-top: 0.2rem;">${idx + 1}</span>
      <textarea class="form-control" placeholder="Describe this cooking step..." onchange="editorSteps[${idx}].instruction = this.value">${escapeHtml(st.instruction)}</textarea>
      <button type="button" class="btn-icon" style="color: var(--danger); margin-top: 0.2rem;" onclick="removeEditorStep(${idx})">✕</button>
    </div>
  `).join("");
}

function addEditorStep() {
  editorSteps.push({ step_number: editorSteps.length + 1, instruction: "" });
  renderEditorSteps();
}

function removeEditorStep(idx) {
  editorSteps.splice(idx, 1);
  renderEditorSteps();
}

async function handleRecipeEditorSubmit(e) {
  e.preventDefault();
  const recipeId = document.getElementById("editor-recipe-id").value;
  const isEdit = Boolean(recipeId);

  const title = document.getElementById("editor-title").value.trim();
  const description = document.getElementById("editor-desc").value.trim();
  const prep_time_min = parseInt(document.getElementById("editor-prep").value) || 0;
  const cook_time_min = parseInt(document.getElementById("editor-cook").value) || 0;
  const servings = parseInt(document.getElementById("editor-servings").value) || 4;
  const difficulty = document.getElementById("editor-difficulty").value;
  const cuisine = document.getElementById("editor-cuisine").value;
  const tags = document.getElementById("editor-tags").value.split(",").map(s => s.trim()).filter(Boolean);
  const image_url = document.getElementById("editor-image-url").value.trim();

  const validIngredients = editorIngredients.filter(i => i.name.trim().length > 0);
  const validSteps = editorSteps.map((s, idx) => ({ step_number: idx + 1, instruction: s.instruction.trim() })).filter(s => s.instruction.length > 0);

  if (!title) {
    showToast("Please enter a recipe title", "error");
    return;
  }
  if (validIngredients.length === 0) {
    showToast("Please add at least one ingredient", "error");
    return;
  }
  if (validSteps.length === 0) {
    showToast("Please add at least one step", "error");
    return;
  }

  const payload = {
    title, description, prep_time_min, cook_time_min, servings,
    difficulty, cuisine, tags, ingredients: validIngredients, steps: validSteps,
    image_url, is_public: 1
  };

  try {
    const url = isEdit ? `/api/recipes/${recipeId}` : "/api/recipes";
    const method = isEdit ? "PUT" : "POST";
    const res = await apiRequest(url, { method, body: JSON.stringify(payload) });

    showToast(res.message, "success");
    closeRecipeEditorModal();
    if (isEdit) {
      viewRecipeDetail(recipeId);
    } else {
      loadRecipesView("mine");
    }
  } catch (err) {
    showToast("Save error: " + err.message, "error");
  }
}
