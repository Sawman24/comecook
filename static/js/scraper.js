/* ==============================================================================
   COOKED - Web & Text Recipe Scraper Engine Client
   ============================================================================== */

let scrapedRecipeDraft = null;
let currentScraperTab = "url";

function openScraperModal() {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }

  const modal = document.getElementById("scraper-modal");
  if (!modal) return;

  scrapedRecipeDraft = null;
  setScraperTab("url");
  document.getElementById("scraper-url-input").value = "";
  document.getElementById("scraper-text-input").value = "";
  document.getElementById("scraper-preview-area").innerHTML = `
    <div style="text-align: center; padding: 1.5rem; color: var(--text-light);">
      <span style="font-size: 2.2rem; display: block; margin-bottom: 0.5rem;">🌐</span>
      <p style="font-size: 0.88rem;">Paste a URL from any culinary site (NYT Cooking, AllRecipes, Serious Eats, Food Network, Bon Appétit, Tasty, etc.)</p>
    </div>
  `;
  document.getElementById("scraper-save-btn").style.display = "none";
  modal.classList.add("show");
}

function setScraperTab(tab) {
  currentScraperTab = tab;
  const urlTab = document.getElementById("scraper-tab-url");
  const textTab = document.getElementById("scraper-tab-text");
  const urlForm = document.getElementById("scraper-url-form-group");
  const textForm = document.getElementById("scraper-text-form-group");

  if (tab === "url") {
    urlTab?.classList.add("active");
    textTab?.classList.remove("active");
    if (urlForm) urlForm.style.display = "block";
    if (textForm) textForm.style.display = "none";
  } else {
    urlTab?.classList.remove("active");
    textTab?.classList.add("active");
    if (urlForm) urlForm.style.display = "none";
    if (textForm) textForm.style.display = "block";
  }
}

function closeScraperModal() {
  const modal = document.getElementById("scraper-modal");
  if (modal) modal.classList.remove("show");
}

async function handleScrapeSubmit(e) {
  e.preventDefault();
  let inputVal = "";
  if (currentScraperTab === "url") {
    inputVal = document.getElementById("scraper-url-input").value.trim();
  } else {
    inputVal = document.getElementById("scraper-text-input").value.trim();
  }

  if (!inputVal) {
    showToast(currentScraperTab === "url" ? "Please enter a valid recipe URL" : "Please paste recipe text", "error");
    return;
  }

  const previewArea = document.getElementById("scraper-preview-area");
  const saveBtn = document.getElementById("scraper-save-btn");
  previewArea.innerHTML = `
    <div style="text-align: center; padding: 2rem; color: var(--text-muted);">
      <div style="font-size: 1.8rem; animation: spin 1s infinite linear; display: inline-block;">🍳</div>
      <p style="margin-top: 0.5rem; font-weight: 600;">Extracting ingredients and directions...</p>
    </div>
  `;
  saveBtn.style.display = "none";

  try {
    const data = await apiRequest("/api/recipes/scrape", {
      method: "POST",
      body: JSON.stringify({ url: inputVal })
    });

    scrapedRecipeDraft = data.recipe;
    renderScrapedPreview(scrapedRecipeDraft);
    saveBtn.style.display = "inline-flex";
    showToast("Recipe extracted successfully!", "success");
  } catch (err) {
    previewArea.innerHTML = `
      <div style="text-align: center; padding: 1.5rem; color: var(--danger); background: var(--danger-light); border-radius: var(--radius-md);">
        <b>Import Failed</b>
        <p style="font-size: 0.85rem; margin-top: 0.25rem;">${escapeHtml(err.message)}</p>
        <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.5rem;">Tip: If the site blocks automated requests, switch to the <b>"Paste Recipe Text"</b> tab above!</p>
      </div>
    `;
    saveBtn.style.display = "none";
  }
}

function renderScrapedPreview(recipe) {
  const previewArea = document.getElementById("scraper-preview-area");
  if (!previewArea) return;

  const ingsCount = (recipe.ingredients || []).length;
  const stepsCount = (recipe.steps || []).length;

  previewArea.innerHTML = `
    <div style="display: flex; gap: 1rem; background: var(--bg-surface-subtle); padding: 1rem; border-radius: var(--radius-md); border: 1px solid var(--border-color);">
      ${recipe.image_url ? `<img src="${escapeHtml(recipe.image_url)}" style="width: 100px; height: 100px; object-fit: cover; border-radius: var(--radius-sm);" />` : ''}
      <div style="flex: 1;">
        <h4 style="font-size: 1.1rem; margin-bottom: 0.3rem;">${escapeHtml(recipe.title)}</h4>
        <p style="color: var(--text-muted); font-size: 0.82rem; margin-bottom: 0.5rem;">${escapeHtml(recipe.description || '')}</p>
        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
          <span class="badge badge-primary">⏱️ ${(recipe.prep_time_min || 0) + (recipe.cook_time_min || 0)} mins</span>
          <span class="badge badge-success">🍽️ ${recipe.servings || 4} servings</span>
          <span class="badge badge-secondary">🛒 ${ingsCount} ingredients</span>
          <span class="badge badge-secondary">📋 ${stepsCount} steps</span>
        </div>
      </div>
    </div>
  `;
}

async function saveScrapedRecipeToBox() {
  if (!scrapedRecipeDraft) return;

  try {
    const res = await apiRequest("/api/recipes", {
      method: "POST",
      body: JSON.stringify(scrapedRecipeDraft)
    });
    showToast("Recipe saved to your Recipe Box!", "success");
    closeScraperModal();
    viewRecipeDetail(res.recipe_id);
  } catch (err) {
    showToast("Error saving recipe: " + err.message, "error");
  }
}
