/* ==============================================================================
   COOKED - Weekly Meal Planner & Kitchen Workstation
   ============================================================================== */

let currentWeekOffset = 0; // 0 = current week, 1 = next week, -1 = prev week
let currentPlannerView = "board"; // "board" or "agenda"
let selectedDayFilter = "all"; // "all" or "Mon", "Tue", etc.
let currentWeekPlans = [];
let plannerAvailableRecipes = [];
let selectedRecipeForPlan = null;
let currentPlanModalTab = "box";

async function loadPlannerView() {
  if (!currentUser) {
    const container = document.getElementById("main-content-view");
    container.innerHTML = `
      <div style="text-align: center; padding: 3.5rem 1.5rem; background: var(--bg-surface); border-radius: var(--radius-lg); border: 1px solid var(--border-color); box-shadow: var(--shadow-sm); max-width: 600px; margin: 2rem auto;">
        <span style="font-size: 3.2rem; display: block; margin-bottom: 0.75rem;">📅</span>
        <h2 style="font-size: 1.6rem; margin-bottom: 0.5rem;">Chef's Weekly Meal Planner</h2>
        <p style="color: var(--text-muted); margin: 0 auto 1.75rem auto; font-size: 0.95rem; line-height: 1.5;">
          Organize your home cooking, plan weekly menus, and generate interactive shopping lists.
        </p>
        <button class="btn btn-primary btn-lg" onclick="openAuthModal('login')">Log In to Cooked</button>
      </div>
    `;
    return;
  }

  const container = document.getElementById("main-content-view");
  if (!container) return;

  const { startStr, endStr, days, weekLabel } = getWeekDays(currentWeekOffset);

  const dayFilterButtons = [
    { key: "all", label: "All Week" },
    ...days.map(d => ({ key: d.shortName, label: `${d.shortName} (${d.formatted})` }))
  ].map(tab => `
    <button class="planner-day-filter-btn ${selectedDayFilter === tab.key ? 'active' : ''}" onclick="setPlannerDayFilter('${tab.key}')">
      ${tab.label}
    </button>
  `).join("");

  container.innerHTML = `
    <!-- Planner Header Bar -->
    <div class="planner-header-wrap">
      <div class="planner-controls-row">
        <div>
          <h2 style="font-size: 1.45rem; margin-bottom: 0.2rem; display: flex; align-items: center; gap: 0.55rem;">
            <span>📅</span> Weekly Meal Planner
          </h2>
          <p style="color: var(--text-muted); font-size: 0.88rem; margin: 0;">
            ${escapeHtml(weekLabel)}
          </p>
        </div>

        <!-- Controls: Nav, View Mode, Actions -->
        <div style="display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;">
          <!-- Week Navigation -->
          <div class="planner-nav-group">
            <button class="btn-icon" title="Previous Week" onclick="shiftPlannerWeek(-1)" style="padding: 0.3rem 0.6rem; font-size: 0.85rem;">◀</button>
            <button class="btn btn-secondary btn-sm" onclick="currentWeekOffset = 0; selectedDayFilter = 'all'; loadPlannerView();" style="font-size: 0.8rem; padding: 0.3rem 0.75rem;">Today</button>
            <button class="btn-icon" title="Next Week" onclick="shiftPlannerWeek(1)" style="padding: 0.3rem 0.6rem; font-size: 0.85rem;">▶</button>
          </div>

          <!-- View Toggle -->
          <div class="planner-view-toggle">
            <button class="planner-view-btn ${currentPlannerView === 'board' ? 'active' : ''}" onclick="setPlannerViewMode('board')">
              📋 Board
            </button>
            <button class="planner-view-btn ${currentPlannerView === 'agenda' ? 'active' : ''}" onclick="setPlannerViewMode('agenda')">
              📅 Agenda
            </button>
          </div>

          <!-- Actions -->
          <button class="btn btn-primary btn-sm" onclick="openWeeklyGroceryModal('${startStr}', '${endStr}')" style="display: inline-flex; align-items: center; gap: 0.35rem;">
            🛒 Grocery List
          </button>
          <button class="btn btn-secondary btn-sm" onclick="clearCurrentPlannerWeek('${startStr}', '${endStr}')" title="Clear all meals for this week">
            🧹 Clear
          </button>
        </div>
      </div>

      <!-- Day Filter Tabs Bar -->
      <div class="planner-day-filter-bar">
        ${dayFilterButtons}
      </div>

      <!-- Weekly Stats Summary Bar -->
      <div class="planner-stats-bar" id="planner-stats-container">
        <span class="planner-stat-pill">🍽️ Planned: <strong id="stat-planned-count">0 / 28</strong></span>
        <span class="planner-stat-pill">⏱️ Total Cook Time: <strong id="stat-cook-time">0 hrs</strong></span>
        <span class="planner-stat-pill">🥗 Unique Cuisines: <strong id="stat-cuisines">None</strong></span>
      </div>
    </div>

    <!-- Active View Container -->
    <div id="planner-active-view-container">
      <div style="text-align: center; padding: 3rem; color: var(--text-light);">
        <div style="font-size: 2rem; animation: spin 1s infinite linear; display: inline-block;">🍳</div>
        <p style="margin-top: 0.5rem;">Loading your kitchen schedule...</p>
      </div>
    </div>
  `;

  await fetchAndRenderPlanner(startStr, endStr, days);
}

function setPlannerViewMode(mode) {
  currentPlannerView = mode;
  const { startStr, endStr, days } = getWeekDays(currentWeekOffset);
  loadPlannerView();
}

function setPlannerDayFilter(dayKey) {
  selectedDayFilter = dayKey;
  const { startStr, endStr, days } = getWeekDays(currentWeekOffset);
  loadPlannerView();
}

function shiftPlannerWeek(delta) {
  currentWeekOffset += delta;
  loadPlannerView();
}

function getWeekDays(offset = 0) {
  const now = new Date();
  const currentDay = now.getDay(); // 0 is Sunday
  const distanceToMonday = (currentDay + 6) % 7;
  
  const monday = new Date(now);
  monday.setDate(now.getDate() - distanceToMonday + (offset * 7));
  monday.setHours(0, 0, 0, 0);

  const todayStr = (typeof formatLocalDate === "function") ? formatLocalDate(new Date()) : new Date().toISOString().split("T")[0];
  const days = [];
  const dayNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const shortNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  for (let i = 0; i < 7; i++) {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    const dateStr = (typeof formatLocalDate === "function") ? formatLocalDate(d) : d.toISOString().split("T")[0];
    days.push({
      dateStr,
      dayName: dayNames[i],
      shortName: shortNames[i],
      formatted: d.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      isToday: dateStr === todayStr
    });
  }

  const startMonth = days[0].formatted;
  const endMonth = days[6].formatted;
  const year = monday.getFullYear();

  return {
    startStr: days[0].dateStr,
    endStr: days[6].dateStr,
    weekLabel: `${startMonth} – ${endMonth}, ${year}`,
    days
  };
}

async function fetchAndRenderPlanner(startStr, endStr, days) {
  try {
    const data = await apiRequest(`/api/planner?start_date=${startStr}&end_date=${endStr}`);
    currentWeekPlans = data.planner || [];
    updatePlannerStats(currentWeekPlans);

    const viewContainer = document.getElementById("planner-active-view-container");
    if (!viewContainer) return;

    const filteredDays = selectedDayFilter === "all" 
      ? days 
      : days.filter(d => d.shortName === selectedDayFilter);

    if (currentPlannerView === "board") {
      renderBoardView(filteredDays, currentWeekPlans);
    } else {
      renderAgendaView(filteredDays, currentWeekPlans);
    }
  } catch (err) {
    showToast("Error loading meal planner: " + err.message, "error");
  }
}

function updatePlannerStats(plans) {
  const plannedCountEl = document.getElementById("stat-planned-count");
  const cookTimeEl = document.getElementById("stat-cook-time");
  const cuisinesEl = document.getElementById("stat-cuisines");

  if (!plannedCountEl) return;

  const totalPlanned = plans.length;
  plannedCountEl.textContent = `${totalPlanned} / 28`;

  let totalMinutes = 0;
  const cuisinesSet = new Set();

  plans.forEach(p => {
    if (p.recipe_time) {
      totalMinutes += parseInt(p.recipe_time) || 0;
    }
    if (p.recipe_cuisine && p.recipe_cuisine !== "Global") {
      cuisinesSet.add(p.recipe_cuisine);
    }
  });

  const hours = (totalMinutes / 60).toFixed(1);
  cookTimeEl.textContent = totalMinutes > 0 ? `${hours} hrs` : "0 mins";

  if (cuisinesSet.size > 0) {
    cuisinesEl.textContent = Array.from(cuisinesSet).slice(0, 3).join(", ");
  } else {
    cuisinesEl.textContent = totalPlanned > 0 ? "Homestyle" : "None";
  }
}

/* ==============================================================================
   1. BOARD VIEW RENDERER (Spacious, Uncongested Columns)
   ============================================================================== */

function renderBoardView(days, plans) {
  const container = document.getElementById("planner-active-view-container");
  if (!container) return;

  const mealTypeMeta = {
    breakfast: { key: "breakfast", label: "Breakfast", icon: "🌅" },
    lunch: { key: "lunch", label: "Lunch", icon: "☀️" },
    dinner: { key: "dinner", label: "Dinner", icon: "🌙" },
    snack: { key: "snack", label: "Snack", icon: "🍎" }
  };

  const isSingleDay = days.length === 1;

  const colsHtml = days.map(day => {
    const dayPlans = plans.filter(p => p.plan_date === day.dateStr);

    let slotsContent = "";
    if (dayPlans.length === 0) {
      slotsContent = `
        <div class="planner-empty-day-state" onclick="openAddPlanModal('${day.dateStr}', 'dinner')">
          <span style="font-size: 1.8rem; opacity: 0.6;">🍽️</span>
          <div style="font-weight: 600; font-size: 0.9rem; color: var(--text-main); margin-top: 0.25rem;">+ Plan a Dish</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">No meals scheduled for ${day.shortName}</div>
        </div>
      `;
    } else {
      const cardsHtml = dayPlans.map(plan => {
        const type = mealTypeMeta[plan.meal_type] || { key: plan.meal_type, label: plan.meal_type, icon: "🍽️" };
        return renderMealCardHtml(plan, type);
      }).join("");

      slotsContent = `
        ${cardsHtml}
        <button class="planner-add-dish-btn" onclick="openAddPlanModal('${day.dateStr}', 'dinner')">
          <span>+</span> Add Another Meal
        </button>
      `;
    }

    return `
      <div class="planner-day-col ${day.isToday ? 'is-today' : ''}" style="${isSingleDay ? 'max-width: 650px; margin: 0 auto;' : ''}">
        <div class="planner-day-header">
          <div>
            <div class="planner-day-title">${day.dayName}</div>
            <div class="planner-day-date">${day.formatted}</div>
          </div>
          ${day.isToday ? `<span class="planner-today-badge">TODAY</span>` : ''}
        </div>
        <div class="planner-day-slots">
          ${slotsContent}
        </div>
      </div>
    `;
  }).join("");

  container.innerHTML = `
    <div class="planner-board-wrapper">
      <div class="planner-board-grid" style="${isSingleDay ? 'display: block;' : ''}">
        ${colsHtml}
      </div>
    </div>
  `;
}

function renderMealCardHtml(plan, type) {
  const title = escapeHtml(plan.recipe_title || plan.custom_title || "Planned Meal");
  const time = plan.recipe_time ? `⏱️ ${plan.recipe_time}m` : '';
  const cuisine = plan.recipe_cuisine && plan.recipe_cuisine !== 'Global' ? plan.recipe_cuisine : '';

  return `
    <div class="planner-meal-card">
      <div class="planner-meal-tag-row">
        <span class="planner-meal-tag-${type.key}">${type.icon} ${type.label}</span>
        <button class="btn-icon" title="Remove meal" style="font-size: 0.75rem; color: var(--danger); padding: 2px;" onclick="deletePlanSlot(${plan.id})">✕</button>
      </div>

      <div class="planner-card-body">
        ${plan.recipe_image ? `
          <img src="${escapeHtml(plan.recipe_image)}" class="planner-card-thumb" alt="${title}" onerror="this.outerHTML='<div class=\\'planner-card-thumb-placeholder\\'>🍽️</div>'" />
        ` : `
          <div class="planner-card-thumb-placeholder">🍽️</div>
        `}
        <div class="planner-card-info">
          <div class="planner-card-title" title="${title}" onclick="${plan.recipe_id ? `viewRecipeDetail(${plan.recipe_id})` : ''}">
            ${title}
          </div>
          <div class="planner-card-meta">
            ${time ? `<span>${time}</span>` : ''}
            ${cuisine ? `<span>• ${escapeHtml(cuisine)}</span>` : ''}
          </div>
        </div>
      </div>

      ${plan.notes ? `
        <div class="planner-card-notes">
          📝 ${escapeHtml(plan.notes)}
        </div>
      ` : ''}

      ${plan.recipe_id ? `
        <div class="planner-card-actions">
          <button class="planner-cook-btn" onclick="startStepCookingForPlan(${plan.recipe_id})">
            ▶ Cook Now
          </button>
          <span style="font-size: 0.72rem; color: var(--text-muted);">Recipe Box</span>
        </div>
      ` : ''}
    </div>
  `;
}

/* ==============================================================================
   2. AGENDA VIEW RENDERER (Day-by-Day Deep Dive)
   ============================================================================== */

function renderAgendaView(days, plans) {
  const container = document.getElementById("planner-active-view-container");
  if (!container) return;

  const mealTypeMeta = {
    breakfast: { key: "breakfast", label: "Breakfast", icon: "🌅" },
    lunch: { key: "lunch", label: "Lunch", icon: "☀️" },
    dinner: { key: "dinner", label: "Dinner", icon: "🌙" },
    snack: { key: "snack", label: "Snack", icon: "🍎" }
  };

  const daysHtml = days.map(day => {
    const dayPlans = plans.filter(p => p.plan_date === day.dateStr);

    let mealsHtml = "";
    if (dayPlans.length === 0) {
      mealsHtml = `
        <div style="grid-column: 1/-1; padding: 1.5rem; text-align: center; border: 1.5px dashed var(--border-color); border-radius: var(--radius-md); cursor: pointer; background: var(--bg-surface-subtle);" onclick="openAddPlanModal('${day.dateStr}', 'dinner')">
          <span style="color: var(--text-muted); font-size: 0.88rem; font-weight: 500;">+ No meals planned for ${day.dayName}. Click to add a dish!</span>
        </div>
      `;
    } else {
      mealsHtml = dayPlans.map(plan => {
        const type = mealTypeMeta[plan.meal_type] || { key: plan.meal_type, label: plan.meal_type, icon: "🍽️" };
        return renderMealCardHtml(plan, type);
      }).join("") + `
        <div style="border: 1.5px dashed var(--border-color); border-radius: var(--radius-md); display: flex; align-items: center; justify-content: center; cursor: pointer; min-height: 90px; padding: 1rem; color: var(--text-muted); font-weight: 600; font-size: 0.85rem;" onclick="openAddPlanModal('${day.dateStr}', 'dinner')">
          + Add Another Meal
        </div>
      `;
    }

    return `
      <div class="planner-agenda-day-card ${day.isToday ? 'is-today' : ''}">
        <div class="planner-agenda-day-head">
          <div style="display: flex; align-items: center; gap: 0.75rem;">
            <h3 style="margin: 0; font-size: 1.15rem;">${day.dayName}</h3>
            <span style="color: var(--text-muted); font-size: 0.9rem;">${day.formatted}</span>
            ${day.isToday ? `<span class="planner-today-badge">TODAY</span>` : ''}
          </div>
          <span style="font-size: 0.82rem; color: var(--text-muted); font-weight: 500;">${dayPlans.length} dish${dayPlans.length === 1 ? '' : 'es'} planned</span>
        </div>
        <div class="planner-agenda-meals-grid">
          ${mealsHtml}
        </div>
      </div>
    `;
  }).join("");

  container.innerHTML = `
    <div class="planner-agenda-container">
      ${daysHtml}
    </div>
  `;
}

/* ==============================================================================
   3. ADD MEAL MODAL & RECIPE PICKER
   ============================================================================== */

function openAddPlanModal(dateStr, mealType) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }

  const modal = document.getElementById("planner-modal");
  if (!modal) return;

  const todayStr = (typeof formatLocalDate === "function") ? formatLocalDate(new Date()) : new Date().toISOString().split("T")[0];
  document.getElementById("plan-date-input").value = dateStr || todayStr;
  document.getElementById("plan-meal-type-select").value = mealType || "dinner";
  document.getElementById("plan-custom-title").value = "";
  document.getElementById("plan-notes").value = "";
  document.getElementById("plan-selected-recipe-id").value = "";
  selectedRecipeForPlan = null;

  setPlanModalTab("box");
  loadPlannerRecipesVisualPicker();

  modal.classList.add("show");
}

function closePlannerModal() {
  const modal = document.getElementById("planner-modal");
  if (modal) modal.classList.remove("show");
}

function setPlanModalTab(tab) {
  currentPlanModalTab = tab;
  const tabBox = document.getElementById("plan-tab-box");
  const tabCustom = document.getElementById("plan-tab-custom");
  const secBox = document.getElementById("plan-section-box");
  const secCustom = document.getElementById("plan-section-custom");

  if (tab === "box") {
    tabBox?.classList.add("active");
    tabCustom?.classList.remove("active");
    if (secBox) secBox.style.display = "block";
    if (secCustom) secCustom.style.display = "none";
  } else {
    tabBox?.classList.remove("active");
    tabCustom?.classList.add("active");
    if (secBox) secBox.style.display = "none";
    if (secCustom) secCustom.style.display = "block";
  }
}

async function loadPlannerRecipesVisualPicker() {
  const grid = document.getElementById("plan-recipe-picker-grid");
  if (!grid) return;

  grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 1.5rem; color: var(--text-light);">Loading your Recipe Box...</div>`;

  try {
    const data = await apiRequest("/api/recipes?scope=all");
    plannerAvailableRecipes = data.recipes || [];
    renderRecipePickerCards(plannerAvailableRecipes);
  } catch (err) {
    grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 1rem; color: var(--danger);">Failed to load recipes.</div>`;
  }
}

function renderRecipePickerCards(recipes) {
  const grid = document.getElementById("plan-recipe-picker-grid");
  if (!grid) return;

  if (recipes.length === 0) {
    grid.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 1.5rem; color: var(--text-muted); font-size: 0.85rem;">
        No recipes found in your box. Switch to the <b>Custom Dish</b> tab to add a meal manually!
      </div>
    `;
    return;
  }

  const selectedId = document.getElementById("plan-selected-recipe-id").value;

  grid.innerHTML = recipes.map(r => `
    <div class="planner-picker-card ${selectedId === String(r.id) ? 'selected' : ''}" onclick="selectPlannerRecipe(${r.id}, event)">
      ${r.image_url ? `
        <img src="${escapeHtml(r.image_url)}" class="planner-picker-thumb" alt="${escapeHtml(r.title)}" onerror="this.outerHTML='<div class=\\'planner-picker-thumb\\' style=\\'display:flex;align-items:center;justify-content:center;background:var(--bg-surface-subtle);\\'>🍽️</div>'" />
      ` : `
        <div class="planner-picker-thumb" style="display:flex;align-items:center;justify-content:center;background:var(--bg-surface-subtle);">🍽️</div>
      `}
      <div style="flex: 1; min-width: 0;">
        <div class="planner-picker-title">${escapeHtml(r.title)}</div>
        <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">
          ⏱️ ${(r.prep_time_min || 0) + (r.cook_time_min || 0)}m ${r.cuisine ? `• ${escapeHtml(r.cuisine)}` : ''}
        </div>
      </div>
    </div>
  `).join("");
}

function filterPlannerRecipes(query) {
  const q = query.trim().toLowerCase();
  if (!q) {
    renderRecipePickerCards(plannerAvailableRecipes);
    return;
  }

  const filtered = plannerAvailableRecipes.filter(r => 
    (r.title && r.title.toLowerCase().includes(q)) ||
    (r.cuisine && r.cuisine.toLowerCase().includes(q)) ||
    (r.difficulty && r.difficulty.toLowerCase().includes(q))
  );

  renderRecipePickerCards(filtered);
}

function selectPlannerRecipe(recipeId, evt) {
  const idInput = document.getElementById("plan-selected-recipe-id");
  idInput.value = recipeId;

  // Update selected classes in DOM
  const cards = document.querySelectorAll(".planner-picker-card");
  cards.forEach(card => card.classList.remove("selected"));

  const target = evt?.currentTarget || event?.currentTarget;
  if (target) {
    target.classList.add("selected");
  }
}

async function handleAddPlanSubmit(e) {
  e.preventDefault();
  const plan_date = document.getElementById("plan-date-input").value;
  const meal_type = document.getElementById("plan-meal-type-select").value;
  const custom_title = document.getElementById("plan-custom-title").value.trim();
  const notes = document.getElementById("plan-notes").value.trim();
  const selectedRecipeId = document.getElementById("plan-selected-recipe-id").value;

  let recipe_id = null;
  if (currentPlanModalTab === "box" && selectedRecipeId) {
    recipe_id = parseInt(selectedRecipeId);
  }

  if (!recipe_id && !custom_title) {
    showToast("Please select a recipe or enter a custom meal title", "error");
    return;
  }

  try {
    await apiRequest("/api/planner", {
      method: "POST",
      body: JSON.stringify({
        plan_date,
        meal_type,
        recipe_id,
        custom_title: currentPlanModalTab === "custom" ? custom_title : "",
        notes
      })
    });

    showToast("Meal added to your plan!", "success");
    closePlannerModal();
    loadPlannerView();
  } catch (err) {
    showToast("Error adding meal: " + err.message, "error");
  }
}

async function deletePlanSlot(planId) {
  try {
    await apiRequest(`/api/planner/${planId}`, { method: "DELETE" });
    showToast("Meal removed from plan", "info");
    loadPlannerView();
  } catch (err) {
    showToast("Error removing meal: " + err.message, "error");
  }
}

async function clearCurrentPlannerWeek(startStr, endStr) {
  if (!confirm(`Are you sure you want to clear all planned meals for ${startStr} to ${endStr}?`)) {
    return;
  }

  try {
    const res = await apiRequest("/api/planner/clear-week", {
      method: "POST",
      body: JSON.stringify({ start_date: startStr, end_date: endStr })
    });
    showToast(res.message || "Week cleared", "info");
    loadPlannerView();
  } catch (err) {
    showToast("Error clearing week: " + err.message, "error");
  }
}

function startStepCookingForPlan(recipeId) {
  viewRecipeDetail(recipeId);
  setTimeout(() => {
    const cookSection = document.getElementById("recipe-cooking-checklist-section");
    if (cookSection) {
      cookSection.scrollIntoView({ behavior: "smooth" });
    }
  }, 350);
}

/* ==============================================================================
   4. WEEKLY GROCERY LIST GENERATOR
   ============================================================================== */

let currentWeeklyGroceryData = null;

async function openWeeklyGroceryModal(startStr, endStr) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }

  const modal = document.getElementById("planner-grocery-modal");
  const content = document.getElementById("planner-grocery-content");
  const countEl = document.getElementById("planner-grocery-count");
  const subtitle = document.getElementById("planner-grocery-subtitle");

  if (!modal || !content) return;

  subtitle.textContent = `Ingredients for ${startStr} to ${endStr}`;
  content.innerHTML = `
    <div style="text-align: center; padding: 2rem; color: var(--text-muted);">
      <div style="font-size: 1.8rem; animation: spin 1s infinite linear; display: inline-block;">🛒</div>
      <p style="margin-top: 0.5rem; font-weight: 600;">Compiling ingredient checklist across all scheduled recipes...</p>
    </div>
  `;
  modal.classList.add("show");

  try {
    const data = await apiRequest(`/api/planner/grocery-list?start_date=${startStr}&end_date=${endStr}`);
    currentWeeklyGroceryData = data;
    renderGroceryChecklist(data);
  } catch (err) {
    content.innerHTML = `
      <div style="text-align: center; padding: 1.5rem; color: var(--danger);">
        Error loading grocery list: ${escapeHtml(err.message)}
      </div>
    `;
  }
}

function closePlannerGroceryModal() {
  const modal = document.getElementById("planner-grocery-modal");
  if (modal) modal.classList.remove("show");
}

function renderGroceryChecklist(data) {
  const content = document.getElementById("planner-grocery-content");
  const countEl = document.getElementById("planner-grocery-count");
  if (!content) return;

  const categories = data.categories || {};
  const catNames = Object.keys(categories);
  const catIcons = {
    "Produce": "🥦",
    "Dairy": "🧀",
    "Meat": "🥩",
    "Bakery": "🍞",
    "Spices": "🌿",
    "Pantry": "🥫"
  };

  let totalItems = 0;
  let html = "";

  catNames.forEach(cat => {
    const items = categories[cat] || [];
    if (items.length > 0) {
      totalItems += items.length;
      const icon = catIcons[cat] || "🛒";

      const itemsHtml = items.map((item, idx) => `
        <div class="grocery-item-row" id="grocery-row-${cat}-${idx}">
          <input type="checkbox" onchange="toggleGroceryCheck(this, 'grocery-row-${cat}-${idx}')" />
          <span><strong>${escapeHtml(item.display)}</strong></span>
          <span class="grocery-item-source">(${escapeHtml(item.recipe_title)})</span>
        </div>
      `).join("");

      html += `
        <div class="grocery-category-group">
          <div class="grocery-category-header">
            <span>${icon} ${cat}</span>
            <span style="font-size: 0.78rem; color: var(--text-muted); font-weight: normal;">${items.length} items</span>
          </div>
          <div>${itemsHtml}</div>
        </div>
      `;
    }
  });

  if (totalItems === 0) {
    content.innerHTML = `
      <div style="text-align: center; padding: 2.5rem; color: var(--text-muted);">
        <span style="font-size: 2.5rem; display: block; margin-bottom: 0.5rem;">🍽️</span>
        <h4>No Recipe Ingredients Scheduled</h4>
        <p style="font-size: 0.85rem; margin-top: 0.25rem;">
          Schedule dishes from your Recipe Box to auto-generate a categorized shopping list for this week!
        </p>
      </div>
    `;
    if (countEl) countEl.textContent = "0 items";
    return;
  }

  content.innerHTML = html;
  if (countEl) countEl.textContent = `${totalItems} items across ${catNames.filter(c => (categories[c]||[]).length > 0).length} departments`;
}

function toggleGroceryCheck(checkbox, rowId) {
  const row = document.getElementById(rowId);
  if (row) {
    if (checkbox.checked) {
      row.classList.add("checked");
    } else {
      row.classList.remove("checked");
    }
  }
}

function copyGroceryListToClipboard() {
  if (!currentWeeklyGroceryData || !currentWeeklyGroceryData.categories) {
    showToast("No grocery items to copy", "info");
    return;
  }

  const categories = currentWeeklyGroceryData.categories;
  let text = `🛒 Cooked Weekly Grocery List (${currentWeeklyGroceryData.start_date} to ${currentWeeklyGroceryData.end_date})\n\n`;

  Object.keys(categories).forEach(cat => {
    const items = categories[cat] || [];
    if (items.length > 0) {
      text += `--- ${cat.toUpperCase()} ---\n`;
      items.forEach(item => {
        text += `[ ] ${item.display} (${item.recipe_title})\n`;
      });
      text += `\n`;
    }
  });

  navigator.clipboard.writeText(text).then(() => {
    showToast("Grocery checklist copied to clipboard!", "success");
  }).catch(() => {
    showToast("Copied to clipboard", "success");
  });
}

