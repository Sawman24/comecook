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

  const isHeroVisible = scope === "all";

  container.innerHTML = `
    ${isHeroVisible ? `
      <!-- Kitchen Hub Hero Inspiration Banner -->
      <div class="kitchen-hub-hero">
        <div class="kitchen-hub-hero-content">
          <div class="kitchen-hub-hero-tag">🌟 Chef's Daily Inspiration</div>
          <h1>Artisan Sourdough Boule & Herb Butter</h1>
          <p>Open airy crumb with blistered cast-iron crust. Master wild yeast fermentation, dough hydration, and Dutch oven steam baking.</p>
          <div class="kitchen-hub-hero-actions">
            <button class="btn-hero-primary" onclick="openRecipeEditorModal()">
              <span>🍳</span> Write New Recipe
            </button>
            <button class="btn-hero-secondary" onclick="openScraperModal()">
              <span>🔗</span> Import from Web URL
            </button>
          </div>
        </div>
      </div>
    ` : `
      <div class="recipe-box-header" style="margin-bottom: 1.25rem;">
        <div>
          <h2 style="font-size: 1.5rem; margin-bottom: 0.25rem;">${scope === 'mine' ? '👨‍🍳 My Recipe Vault' : '🔖 Saved Recipe Box'}</h2>
          <p style="color: var(--text-muted); font-size: 0.88rem;">${scope === 'mine' ? 'Recipes crafted and adapted by you' : 'Your saved community bookmarks and favorites'}</p>
        </div>
        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
          <button class="btn btn-secondary btn-sm" onclick="openScraperModal()">
            <span>🔗</span> Import Web Recipe
          </button>
          <button class="btn btn-primary btn-sm" onclick="openRecipeEditorModal()">
            <span>+</span> Write Recipe
          </button>
        </div>
      </div>
    `}

    <!-- Top Trending Tags Strip (Compact 1-Line) -->
    <div class="hub-trending-strip" id="trending-topics-bar">
      <div class="hub-trending-label">🔥 Trending:</div>
      <div class="hub-trending-tags-scroll" id="trending-topics-list">
        <span class="trending-placeholder" style="font-size: 0.75rem; color: var(--text-light);">Loading tags...</span>
      </div>
    </div>

    <!-- Segmented Navigation & Filter Bar -->
    <div class="hub-control-bar">
      <div class="segmented-control">
        <button class="segmented-btn ${scope === 'all' ? 'active' : ''}" onclick="loadRecipesView('all')">
          <span>🌟</span> Discover
        </button>
        <button class="segmented-btn ${scope === 'mine' ? 'active' : ''}" onclick="loadRecipesView('mine')">
          <span>👨‍🍳</span> My Box
        </button>
        <button class="segmented-btn ${scope === 'saved' ? 'active' : ''}" onclick="loadRecipesView('saved')">
          <span>🔖</span> Saved Vault
        </button>
      </div>

      <div style="display: flex; gap: 0.5rem; align-items: center;">
        <button class="filter-toggle-btn" id="recipe-filter-btn" onclick="toggleRecipeFilterDrawer()">
          <span>⚙️</span> Filters <span style="font-size: 0.75rem;">▾</span>
        </button>
      </div>
    </div>

    <!-- Collapsible Filter Drawer -->
    <div class="filter-drawer-panel" id="recipe-filter-drawer">
      <div class="filter-drawer-grid">
        <div class="filter-drawer-col">
          <label>Cuisine</label>
          <select id="recipe-cuisine-filter" class="form-control" style="font-size: 0.85rem;" onchange="applyRecipeFilters()">
            <option value="All">All Cuisines</option>
            <option value="Italian">Italian</option>
            <option value="French / Artisan">French / Artisan</option>
            <option value="American">American</option>
            <option value="Mexican">Mexican</option>
            <option value="Asian">Asian</option>
            <option value="Mediterranean">Mediterranean</option>
          </select>
        </div>
        <div class="filter-drawer-col">
          <label>Difficulty</label>
          <select id="recipe-difficulty-filter" class="form-control" style="font-size: 0.85rem;" onchange="applyRecipeFilters()">
            <option value="All">All Difficulties</option>
            <option value="Easy">Easy (&lt;30m)</option>
            <option value="Medium">Medium</option>
            <option value="Advanced">Advanced (Artisan)</option>
          </select>
        </div>
      </div>
    </div>

    <div id="recipe-grid-container" class="recipe-grid">
      <div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: var(--text-light);">
        Loading culinary vault...
      </div>
    </div>
  `;

  if (typeof fetchAndRenderTrendingHashtags === "function") {
    fetchAndRenderTrendingHashtags();
  }
  await fetchAndRenderRecipes();
}

function toggleRecipeFilterDrawer() {
  const drawer = document.getElementById("recipe-filter-drawer");
  const btn = document.getElementById("recipe-filter-btn");
  if (drawer) {
    drawer.classList.toggle("open");
    if (btn) btn.classList.toggle("has-filters", drawer.classList.contains("open"));
  }
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
            ${currentRecipeScope === 'saved' ? 'Your saved recipe box is empty. Bookmark community recipes to see them here!' : 'Try adjusting your filters or write a new recipe!'}
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
  const tags = (recipe.tags || []).slice(0, 3).map(t => `<span class="badge badge-secondary" style="font-size: 0.72rem;">#${escapeHtml(t)}</span>`).join(" ");
  const defaultImg = "https://images.unsplash.com/photo-1495521821757-a1efb6729352?w=600&auto=format&fit=crop&q=80";
  const ratingHtml = recipe.avg_rating > 0 
    ? `<span class="recipe-rating-badge" title="${recipe.avg_rating} out of 5 stars (${recipe.reviews_count || 0} reviews)">★ ${recipe.avg_rating} <span style="opacity:0.75; font-weight:normal;">(${recipe.reviews_count || 0})</span></span>`
    : '';

  const forkBadgeHtml = (recipe.fork_count && recipe.fork_count > 0)
    ? `<span class="recipe-card-fork-pill" title="${recipe.fork_count} community variations/twists">🌿 ${recipe.fork_count}</span>`
    : '';

  const totalTime = (recipe.prep_time_min || 0) + (recipe.cook_time_min || 0);

  return `
    <div class="recipe-card" onclick="viewRecipeDetail(${recipe.id})">
      <div class="recipe-card-img-wrap">
        <img src="${escapeHtml(recipe.image_url || defaultImg)}" alt="${escapeHtml(recipe.title)}" />
        ${forkBadgeHtml}
        <span class="recipe-card-time-pill">⏱️ ${totalTime > 0 ? totalTime + 'm' : '30m'}</span>
      </div>
      <div class="recipe-card-body">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.35rem;">
          <div style="display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap;">
            <span class="badge badge-primary">${escapeHtml(recipe.cuisine || 'Global')}</span>
            ${ratingHtml}
          </div>
          <button class="btn-icon" style="padding: 2px;" onclick="event.stopPropagation(); toggleSaveRecipe(${recipe.id}, this)">
            ${recipe.is_saved ? '❤️' : '🤍'}
          </button>
        </div>
        <h3 class="recipe-card-title">${escapeHtml(recipe.title)}</h3>
        <p style="color: var(--text-muted); font-size: 0.82rem; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; margin-bottom: 0.5rem;">
          ${escapeHtml(recipe.description || '')}
        </p>
        <div class="recipe-card-tags" style="margin-bottom: 0.65rem;">${tags}</div>
        <div class="recipe-card-meta">
          <span style="display: flex; align-items: center; gap: 0.3rem;">
            <span>📊</span> ${escapeHtml(recipe.difficulty || 'Medium')}
          </span>
          <span style="display: flex; align-items: center; gap: 0.3rem;">
            <span>🍽️</span> ${recipe.servings || 4} serv
          </span>
          <span style="margin-left: auto; font-size: 0.75rem; color: var(--text-light);">
            by @${escapeHtml(recipe.author_username || 'chef')}
          </span>
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
    fetchAndRenderRecipeReviews(recipeId);
    fetchAndRenderRecipeForks(recipeId);
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

  const tagsHtml = (r.tags || []).map(t => `<span class="badge badge-secondary" style="cursor: pointer;" onclick="openHashtagFeed('${escapeHtml(t)}')">#${escapeHtml(t)}</span>`).join(" ");

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
      <div class="instruction-step-item" id="step-row-${idx}">
        <input type="checkbox" class="step-checkbox" onchange="toggleStepComplete(${idx}, this)" id="step-chk-${idx}" />
        <label class="step-content" for="step-chk-${idx}">
          <span class="step-num">${st.step_number || idx + 1}</span>
          <p class="step-text">${escapeHtml(st.instruction)}</p>
        </label>
      </div>
    `;
  }).join("");

  // Lineage attribution banner if this recipe is a fork
  let lineageBannerHtml = "";
  if (r.parent_recipe) {
    lineageBannerHtml = `
      <div class="recipe-lineage-banner" onclick="viewRecipeDetail(${r.parent_recipe.id})">
        <span style="font-size: 1.4rem;">🌿</span>
        <div style="flex: 1;">
          <div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; color: var(--primary);">Recipe Genealogy • Community Twist</div>
          <div style="font-size: 0.95rem; font-weight: 700; color: var(--text-main);">
            Adapted from <span style="text-decoration: underline; color: var(--primary);">${escapeHtml(r.parent_recipe.title)}</span> by Chef @${escapeHtml(r.parent_recipe.author_username)}
          </div>
          ${r.fork_notes ? `<div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.2rem; font-style: italic;">“${escapeHtml(r.fork_notes)}”</div>` : ''}
        </div>
        <span class="btn btn-outline btn-sm" style="font-size: 0.75rem;">View Original</span>
      </div>
    `;
  }

  container.innerHTML = `
    <div style="margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
      <button class="btn btn-secondary btn-sm" onclick="loadRecipesView('${currentRecipeScope}')">
        ← Back to Recipe Box
      </button>
      <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
        <button class="btn btn-primary btn-sm" onclick="openReviewModal(${r.id}, '${escapeHtml(r.title)}')">
          📸 I Made This!
        </button>
        <button class="btn btn-outline btn-sm" onclick="toggleSaveRecipe(${r.id})">
          ${r.is_saved ? '❤️ Saved to Box' : '🤍 Save to Box'}
        </button>
        <button class="btn btn-secondary btn-sm" onclick="openForkModal(${r.id})">
          🍴 Fork Recipe ${r.forks_count > 0 ? `(${r.forks_count})` : ''}
        </button>
        ${isOwner ? `
          <button class="btn btn-secondary btn-sm" onclick="openRecipeEditorModal(${r.id})">✏️ Edit</button>
          <button class="btn btn-danger btn-sm" onclick="deleteRecipe(${r.id})">🗑️ Delete</button>
        ` : ''}
      </div>
    </div>

    ${lineageBannerHtml}

    <!-- Recipe Hero Banner -->
    <div class="recipe-detail-header">
      ${r.image_url ? `
        <div style="cursor: pointer; position: relative;" onclick="openLightbox('${escapeHtml(r.image_url)}', '${escapeHtml(r.title)}')">
          <img class="recipe-hero-img" src="${escapeHtml(r.image_url)}" alt="${escapeHtml(r.title)}" />
          <span style="position: absolute; bottom: 12px; right: 12px; background: rgba(0,0,0,0.6); color: #fff; padding: 4px 10px; border-radius: var(--radius-full); font-size: 0.8rem;">🔍 Zoom Photo</span>
        </div>
      ` : ''}
      <div class="recipe-hero-content">
        <div style="display: flex; gap: 0.5rem; margin-bottom: 0.5rem; align-items: center; flex-wrap: wrap;">
          <span class="badge badge-primary">${escapeHtml(r.cuisine || 'Global')}</span>
          <span class="badge badge-success">${escapeHtml(r.difficulty || 'Medium')}</span>
          ${r.avg_rating > 0 ? `<span class="recipe-rating-badge">★ ${r.avg_rating} (${r.reviews_count} reviews)</span>` : ''}
        </div>
        <h1 style="font-size: 1.8rem; margin-bottom: 0.5rem;">${escapeHtml(r.title)}</h1>
        <p style="color: var(--text-muted); font-size: 1rem; margin-bottom: 1rem;">${escapeHtml(r.description || '')}</p>
        
        <div style="display: flex; align-items: center; gap: 0.75rem;">
          <img src="${escapeHtml(r.author_avatar || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" />
          <div>
            <span style="font-weight: 700; font-size: 0.9rem; cursor: pointer;" onclick="openUserProfile('${escapeHtml(r.author_username)}')">
              Chef ${escapeHtml(r.author_display_name || r.author_username)}
            </span>
            ${r.parent_recipe ? `<span style="font-size: 0.78rem; color: var(--text-light); display: block;">Forked from @${escapeHtml(r.parent_recipe.author_username)}</span>` : ''}
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
          <div class="meta-badge-box">
            <div class="label">Rating</div>
            <div class="value" style="color: #d97706;">${r.avg_rating > 0 ? `★ ${r.avg_rating}` : 'New'}</div>
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

    <!-- Community Variations & Forks Section -->
    <div class="remakes-section" id="recipe-forks-section" style="margin-bottom: 1.5rem;">
      <div class="remakes-header">
        <div>
          <h3 style="font-size: 1.3rem; margin-bottom: 0.25rem;">🌿 Community Twists & Variations (${r.forks_count || 0})</h3>
          <p style="color: var(--text-muted); font-size: 0.85rem;">Recipes adapted and remixed from this dish by fellow chefs.</p>
        </div>
        <button class="btn btn-secondary btn-sm" onclick="openForkModal(${r.id})">
          <span>🍴</span> Create a Twist
        </button>
      </div>

      <div id="recipe-forks-content">
        <div style="text-align: center; padding: 1.5rem; color: var(--text-light); font-size: 0.88rem;">
          Loading community variations...
        </div>
      </div>
    </div>

    <!-- Community Remakes & Reviews Section -->
    <div class="remakes-section" id="recipe-reviews-section">
      <div class="remakes-header">
        <div>
          <h3 style="font-size: 1.3rem; margin-bottom: 0.25rem;">🍳 Made by the Community</h3>
          <p style="color: var(--text-muted); font-size: 0.85rem;">Cook snaps, star ratings, and chef notes from the brigade.</p>
        </div>
        <button class="btn btn-primary btn-sm" onclick="openReviewModal(${r.id}, '${escapeHtml(r.title)}')">
          <span>📸</span> Post Your Remake
        </button>
      </div>

      <div id="recipe-reviews-content">
        <div style="text-align: center; padding: 1.5rem; color: var(--text-light); font-size: 0.88rem;">
          Loading community creations...
        </div>
      </div>
    </div>
  `;
}

async function fetchAndRenderRecipeForks(recipeId) {
  const container = document.getElementById("recipe-forks-content");
  if (!container) return;

  try {
    const data = await apiRequest(`/api/recipes/${recipeId}/forks`);
    const forks = data.forks || [];

    if (forks.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 2rem 1rem; background: var(--bg-surface); border: 1px dashed var(--border-color); border-radius: var(--radius-md);">
          <span style="font-size: 2rem; display: block; margin-bottom: 0.35rem;">🌿</span>
          <h4>No variations created yet</h4>
          <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.25rem;">Be the first chef to put your own creative spin on this recipe!</p>
          <button class="btn btn-secondary btn-sm" style="margin-top: 0.75rem;" onclick="openForkModal(${recipeId})">
            🍴 Create a Twist
          </button>
        </div>
      `;
      return;
    }

    container.innerHTML = `
      <div class="forks-grid">
        ${forks.map(f => `
          <div class="fork-card" onclick="viewRecipeDetail(${f.id})">
            <div class="fork-card-header">
              <img src="${escapeHtml(f.author_avatar || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" />
              <div>
                <span style="font-weight: 700; font-size: 0.88rem; display: block;">${escapeHtml(f.title)}</span>
                <span style="font-size: 0.75rem; color: var(--text-light);">by @${escapeHtml(f.author_username)}</span>
              </div>
            </div>
            ${f.fork_notes ? `
              <div class="fork-card-notes">
                <span style="color: var(--primary); font-weight: 600;">Twist:</span> “${escapeHtml(f.fork_notes)}”
              </div>
            ` : ''}
            <div class="fork-card-footer">
              <span style="font-size: 0.78rem; color: var(--text-light);">⏱️ ${(f.prep_time_min || 0) + (f.cook_time_min || 0)}m</span>
              <span style="font-size: 0.78rem; color: #d97706;">${f.avg_rating > 0 ? `★ ${f.avg_rating}` : 'New Twist'}</span>
            </div>
          </div>
        `).join("")}
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div style="text-align: center; padding: 1.5rem; color: var(--text-muted); font-size: 0.85rem;">No variations found.</div>`;
  }
}

function openForkModal(recipeId) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }
  const r = (activeRecipeDetail && activeRecipeDetail.id === recipeId) ? activeRecipeDetail : null;
  const modal = document.getElementById("fork-modal");
  if (!modal) {
    forkRecipe(recipeId);
    return;
  }

  document.getElementById("fork-source-recipe-id").value = recipeId;
  document.getElementById("fork-source-title").textContent = r ? r.title : `Recipe #${recipeId}`;
  document.getElementById("fork-source-author").textContent = r ? `by @${r.author_username || 'Chef'}` : "";
  document.getElementById("fork-new-title").value = r ? `${r.title} (My Twist)` : "My Recipe Twist";
  document.getElementById("fork-twist-notes").value = "";

  modal.classList.add("show");
}

function closeForkModal() {
  const modal = document.getElementById("fork-modal");
  if (modal) modal.classList.remove("show");
}

async function handleForkSubmit(e) {
  e.preventDefault();
  const recipeId = document.getElementById("fork-source-recipe-id").value;
  const title = document.getElementById("fork-new-title").value.trim();
  const fork_notes = document.getElementById("fork-twist-notes").value.trim();

  if (!title) {
    showToast("Please enter a title for your recipe twist", "error");
    return;
  }

  try {
    const res = await apiRequest(`/api/recipes/${recipeId}/fork`, {
      method: "POST",
      body: JSON.stringify({ title, fork_notes })
    });
    showToast("Recipe forked! Opening editor for your customizations...", "success");
    closeForkModal();
    await viewRecipeDetail(res.recipe_id);
    openRecipeEditorModal(res.recipe_id);
  } catch (err) {
    showToast("Fork error: " + err.message, "error");
  }
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
    const isSaved = (activeRecipeDetail && activeRecipeDetail.id === recipeId) 
      ? activeRecipeDetail.is_saved 
      : (btnEl && btnEl.textContent.includes('❤️'));
    const method = isSaved ? "DELETE" : "POST";
    const options = { method };
    if (method === "POST") {
      options.body = JSON.stringify({ folder_name: "Favorites" });
    }
    const data = await apiRequest(`/api/recipes/${recipeId}/save`, options);
    
    showToast(data.is_saved ? "Saved to your Recipe Box!" : "Removed from Recipe Box", "success");
    if (activeRecipeDetail && activeRecipeDetail.id === recipeId) {
      activeRecipeDetail.is_saved = data.is_saved;
      renderRecipeDetailView();
      fetchAndRenderRecipeReviews(recipeId);
    } else {
      fetchAndRenderRecipes();
    }
  } catch (err) {
    showToast("Error updating saved status: " + err.message, "error");
  }
}

async function forkRecipe(recipeId) {
  openForkModal(recipeId);
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

async function openRecipeEditorModal(recipeIdToEdit = null) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }

  const modal = document.getElementById("recipe-editor-modal");
  if (!modal) return;

  let isEdit = false;
  let r = null;
  if (recipeIdToEdit) {
    if (activeRecipeDetail && activeRecipeDetail.id === recipeIdToEdit) {
      r = activeRecipeDetail;
      isEdit = true;
    } else {
      try {
        const data = await apiRequest(`/api/recipes/${recipeIdToEdit}`);
        r = data.recipe;
        activeRecipeDetail = r;
        isEdit = true;
      } catch (err) {
        showToast("Error loading recipe to edit: " + err.message, "error");
        return;
      }
    }
  }

  if (!r) {
    r = {
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
  }

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

  // Fork / Lineage Banner in Editor
  const forkBanner = document.getElementById("editor-fork-banner");
  const parentIdInput = document.getElementById("editor-parent-recipe-id");
  const forkNotesInput = document.getElementById("editor-fork-notes");
  if (forkBanner && parentIdInput) {
    if (r.parent_recipe_id) {
      parentIdInput.value = r.parent_recipe_id;
      forkNotesInput.value = r.fork_notes || "";
      const attrEl = document.getElementById("editor-fork-attribution");
      if (attrEl && r.parent_recipe) {
        attrEl.textContent = `Adapted from ${r.parent_recipe.title} by @${r.parent_recipe.author_username}`;
      }
      forkBanner.style.display = "block";
    } else {
      parentIdInput.value = "";
      forkNotesInput.value = "";
      forkBanner.style.display = "none";
    }
  }

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
  const parent_recipe_id = document.getElementById("editor-parent-recipe-id") ? document.getElementById("editor-parent-recipe-id").value : null;
  const fork_notes = document.getElementById("editor-fork-notes") ? document.getElementById("editor-fork-notes").value.trim() : "";

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
    image_url, is_public: 1,
    parent_recipe_id: parent_recipe_id ? parseInt(parent_recipe_id) : null,
    fork_notes
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

/* ==============================================================================
   RECIPE REVIEWS & COOK SNAPS ("I MADE THIS!")
   ============================================================================== */

async function fetchAndRenderRecipeReviews(recipeId) {
  const container = document.getElementById("recipe-reviews-content");
  if (!container) return;

  try {
    const data = await apiRequest(`/api/recipes/${recipeId}/reviews`);
    const reviews = data.reviews || [];
    const photoReviews = reviews.filter(r => r.image_url);

    let photosCarouselHtml = "";
    if (photoReviews.length > 0) {
      photosCarouselHtml = `
        <div style="margin-bottom: 1.5rem;">
          <h4 style="font-size: 0.95rem; margin-bottom: 0.75rem; color: var(--text-main);">📸 Community Dish Snaps (${photoReviews.length})</h4>
          <div class="remakes-carousel">
            ${photoReviews.map(pr => `
              <div class="remake-card">
                <img src="${escapeHtml(pr.image_url)}" class="remake-card-img" onclick="openLightbox('${escapeHtml(pr.image_url)}', 'Cook Snap by @${escapeHtml(pr.username)}')" alt="Dish Snap" />
                <div class="remake-card-body">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 700; font-size: 0.82rem; cursor: pointer;" onclick="openUserProfile('${escapeHtml(pr.username)}')">@${escapeHtml(pr.username)}</span>
                    <span style="color: #f59e0b; font-size: 0.8rem;">${'★'.repeat(pr.rating || 5)}</span>
                  </div>
                </div>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }

    let reviewsListHtml = "";
    if (reviews.length === 0) {
      reviewsListHtml = `
        <div style="text-align: center; padding: 2.5rem 1rem; background: var(--bg-surface); border: 1px dashed var(--border-color); border-radius: var(--radius-md);">
          <span style="font-size: 2.2rem; display: block; margin-bottom: 0.35rem;">🍳</span>
          <h4>No remakes yet</h4>
          <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.25rem;">Be the first chef to cook this recipe and share your snap & rating!</p>
          <button class="btn btn-primary btn-sm" style="margin-top: 0.75rem;" onclick="openReviewModal(${recipeId}, '${escapeHtml(activeRecipeDetail?.title || '')}')">
            I Made This!
          </button>
        </div>
      `;
    } else {
      reviewsListHtml = `
        <div class="reviews-list-container">
          ${reviews.map(rev => {
            const isOwner = currentUser && (currentUser.id === rev.user_id || currentUser.is_admin === 1);
            const stars = '★'.repeat(rev.rating) + '☆'.repeat(5 - rev.rating);
            return `
              <div class="review-item-card">
                <img src="${escapeHtml(rev.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" style="cursor: pointer;" onclick="openUserProfile('${escapeHtml(rev.username)}')" />
                <div class="review-item-main">
                  <div class="review-item-header">
                    <div>
                      <span style="font-weight: 700; font-size: 0.9rem; cursor: pointer;" onclick="openUserProfile('${escapeHtml(rev.username)}')">
                        ${escapeHtml(rev.display_name || rev.username)}
                      </span>
                      <span style="font-size: 0.75rem; color: var(--text-light); margin-left: 0.35rem;">@${escapeHtml(rev.username)} • ${formatTimeAgo(rev.created_at)}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                      <span class="review-item-stars" title="${rev.rating} of 5 stars">${stars}</span>
                      ${isOwner ? `
                        <button class="btn-icon" style="color: var(--danger); font-size: 0.8rem; padding: 2px;" title="Delete Review" onclick="deleteReview(${recipeId}, ${rev.id})">🗑️</button>
                      ` : ''}
                    </div>
                  </div>
                  ${rev.review ? `<p class="review-item-notes">${escapeHtml(rev.review)}</p>` : ''}
                  ${rev.image_url ? `
                    <div style="margin-top: 0.5rem; max-width: 200px;">
                      <img src="${escapeHtml(rev.image_url)}" style="width: 100%; border-radius: var(--radius-sm); cursor: pointer;" onclick="openLightbox('${escapeHtml(rev.image_url)}', 'Cook Snap by @${escapeHtml(rev.username)}')" />
                    </div>
                  ` : ''}
                </div>
              </div>
            `;
          }).join("")}
        </div>
      `;
    }

    container.innerHTML = photosCarouselHtml + reviewsListHtml;
  } catch (err) {
    container.innerHTML = `<div style="text-align: center; padding: 1.5rem; color: var(--danger); font-size: 0.85rem;">Failed to load reviews</div>`;
  }
}

function openReviewModal(recipeId, recipeTitle) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }
  const modal = document.getElementById("review-modal");
  if (!modal) return;

  document.getElementById("review-recipe-id").value = recipeId;
  document.getElementById("review-recipe-subtitle").textContent = `Reviewing: ${recipeTitle || 'Recipe'}`;
  document.getElementById("review-rating-val").value = "5";
  setStarRating(5);
  document.getElementById("review-text-input").value = "";
  document.getElementById("review-photo-url").value = "";
  document.getElementById("review-photo-file-input").value = "";
  
  const previewImg = document.getElementById("review-photo-preview");
  const dropContent = document.getElementById("review-photo-dropzone-content");
  if (previewImg) previewImg.classList.add("hidden");
  if (dropContent) {
    dropContent.classList.remove("hidden");
    dropContent.innerHTML = `
      <span style="font-size: 2rem;">📸</span>
      <p><strong>Click to upload dish snap</strong> or drag and drop</p>
      <span class="upload-hint">JPEG, PNG, WebP up to 16MB</span>
    `;
  }

  // Pre-fill if user has an existing review
  if (activeRecipeDetail && activeRecipeDetail.user_review) {
    const ur = activeRecipeDetail.user_review;
    document.getElementById("review-rating-val").value = ur.rating || 5;
    setStarRating(ur.rating || 5);
    document.getElementById("review-text-input").value = ur.review || "";
    if (ur.image_url) {
      document.getElementById("review-photo-url").value = ur.image_url;
      if (previewImg) {
        previewImg.src = ur.image_url;
        previewImg.classList.remove("hidden");
      }
      if (dropContent) dropContent.classList.add("hidden");
    }
  }

  modal.classList.add("show");
}

function closeReviewModal() {
  const modal = document.getElementById("review-modal");
  if (modal) modal.classList.remove("show");
}

function setStarRating(rating) {
  document.getElementById("review-rating-val").value = rating;
  const starBtns = document.querySelectorAll("#star-rating-picker .star-btn");
  starBtns.forEach(btn => {
    const val = parseInt(btn.getAttribute("data-value"));
    if (val <= rating) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
}

async function handleReviewPhotoSelect(input) {
  const file = input.files[0];
  if (!file) return;

  const dropContent = document.getElementById("review-photo-dropzone-content");
  const previewImg = document.getElementById("review-photo-preview");

  try {
    if (dropContent) {
      dropContent.innerHTML = `<div class="spinner-small"></div><p style="margin-top: 0.5rem; font-size: 0.85rem;">Uploading dish snap...</p>`;
    }
    const uploadedUrl = await uploadImageFile(file);
    document.getElementById("review-photo-url").value = uploadedUrl;
    if (previewImg) {
      previewImg.src = uploadedUrl;
      previewImg.classList.remove("hidden");
    }
    if (dropContent) dropContent.classList.add("hidden");
  } catch (err) {
    showToast("Photo upload failed: " + err.message, "error");
    if (dropContent) {
      dropContent.innerHTML = `
        <span style="font-size: 2rem;">📸</span>
        <p><strong>Click to upload dish snap</strong> or drag and drop</p>
        <span class="upload-hint">JPEG, PNG, WebP up to 16MB</span>
      `;
    }
  }
}

async function handleReviewSubmit(e) {
  e.preventDefault();
  const recipeId = document.getElementById("review-recipe-id").value;
  const rating = parseInt(document.getElementById("review-rating-val").value) || 5;
  const review = document.getElementById("review-text-input").value.trim();
  const image_url = document.getElementById("review-photo-url").value.trim();
  const share_to_feed = document.getElementById("review-share-feed").checked;

  const submitBtn = document.getElementById("review-submit-btn");
  submitBtn.disabled = true;
  submitBtn.textContent = "Posting Remake...";

  try {
    const res = await apiRequest(`/api/recipes/${recipeId}/reviews`, {
      method: "POST",
      body: JSON.stringify({ rating, review, image_url, share_to_feed })
    });
    showToast(res.message || "Remake shared successfully!", "success");
    closeReviewModal();
    viewRecipeDetail(parseInt(recipeId));
  } catch (err) {
    showToast("Failed to post review: " + err.message, "error");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Post Remake & Rating";
  }
}

async function deleteReview(recipeId, reviewId) {
  if (!confirm("Are you sure you want to delete your review?")) return;
  try {
    const res = await apiRequest(`/api/recipes/${recipeId}/reviews/${reviewId}`, {
      method: "DELETE"
    });
    showToast(res.message || "Review deleted", "success");
    viewRecipeDetail(parseInt(recipeId));
  } catch (err) {
    showToast("Delete error: " + err.message, "error");
  }
}

