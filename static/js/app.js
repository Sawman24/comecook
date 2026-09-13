/* ==============================================================================
   COOKED - Main App Router & View Controller
   ============================================================================== */

let currentActiveView = "recipes"; // 'recipes', 'feed', 'planner', 'stations', 'profile', 'admin'

document.addEventListener("DOMContentLoaded", async () => {
  // Initialize Auth
  await checkAuthStatus();

  // Load Featured Chefs & Right Sidebar Content
  loadRightSidebarData();

  // Initialize Converter
  if (typeof runUnitConversion === "function") {
    runUnitConversion();
  }

  // Handle Password Reset Deep Links (e.g. /#/reset-password?token=... or ?token=...)
  const urlParams = new URLSearchParams(window.location.search);
  let resetToken = urlParams.get("token") || urlParams.get("reset_token");
  if (!resetToken && window.location.hash.includes("token=")) {
    const hashPart = window.location.hash.includes("?") ? window.location.hash.split("?")[1] : window.location.hash;
    const hashParams = new URLSearchParams(hashPart);
    resetToken = hashParams.get("token") || hashParams.get("reset_token");
  }

  if (resetToken && typeof promptResetPassword === "function") {
    setTimeout(() => promptResetPassword(resetToken), 200);
  }

  // Route to initial view based on direct URL pathname or URL hash
  const pathname = window.location.pathname;
  const hash = window.location.hash.replace(/^#\/?/, "");

  if (pathname.startsWith("/recipes/") && pathname.split("/")[2]) {
    const id = pathname.split("/")[2];
    viewRecipeDetail(parseInt(id));
  } else if (pathname.startsWith("/chefs/") && pathname.split("/")[2]) {
    const user = pathname.split("/")[2];
    openUserProfile(user);
  } else if (pathname.startsWith("/stations/") && pathname.split("/")[2]) {
    const slug = pathname.split("/")[2];
    navigateToStation(slug);
  } else if ((pathname.startsWith("/tags/") || pathname.startsWith("/tag/")) && pathname.split("/")[2]) {
    const tag = pathname.split("/")[2];
    openHashtagFeed(tag);
  } else if (pathname.startsWith("/posts/") && pathname.split("/")[2]) {
    const postId = pathname.split("/")[2];
    navigateTo("feed");
    setTimeout(() => openCommentsModal(parseInt(postId)), 300);
  } else if (hash.startsWith("recipe/")) {
    const id = hash.split("/")[1];
    viewRecipeDetail(parseInt(id));
  } else if (hash.startsWith("chef/")) {
    const user = hash.split("/")[1];
    openUserProfile(user);
  } else if (hash.startsWith("station/")) {
    const slug = hash.split("/")[1];
    navigateToStation(slug);
  } else if (hash.startsWith("tag/")) {
    const tag = hash.split("/")[1];
    openHashtagFeed(tag);
  } else if (hash === "my-box" || hash === "my_box") {
    navigateTo("recipes", "mine");
  } else if (["stations", "recipes", "feed", "planner", "admin"].includes(hash)) {
    navigateTo(hash);
  } else {
    navigateTo("recipes");
  }

  // Setup Global Search Input & Instant Live Dropdown
  const searchInput = document.getElementById("global-search-input");
  const searchDropdown = document.getElementById("search-dropdown-results");

  if (searchInput && searchDropdown) {
    searchInput.addEventListener("input", debounce(async (e) => {
      const q = e.target.value.trim();
      if (!q || q.length < 2) {
        searchDropdown.style.display = "none";
        searchDropdown.innerHTML = "";
        return;
      }

      try {
        const res = await apiRequest(`/api/search?q=${encodeURIComponent(q)}`);
        renderGlobalSearchDropdown(res, q);
      } catch (err) {
        console.error("Global search error:", err);
      }
    }, 250));

    // Handle Enter key on search input
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const q = searchInput.value.trim();
        if (q) {
          searchDropdown.style.display = "none";
          if (q.startsWith("@")) {
            const targetUser = q.substring(1).trim();
            if (targetUser) {
              openUserProfile(targetUser);
              return;
            }
          }
          if (currentActiveView === "recipes") {
            fetchAndRenderRecipes(q);
          } else if (currentActiveView === "feed") {
            fetchAndRenderPosts(q);
          } else if (currentActiveView === "stations") {
            fetchAndRenderStations(q);
          } else {
            navigateTo("recipes");
            setTimeout(() => fetchAndRenderRecipes(q), 100);
          }
        }
      } else if (e.key === "Escape") {
        searchDropdown.style.display = "none";
      }
    });

    // Close search dropdown when clicking outside
    document.addEventListener("click", (e) => {
      if (!searchInput.contains(e.target) && !searchDropdown.contains(e.target)) {
        searchDropdown.style.display = "none";
      }
    });

    // Re-open dropdown on focus if input has text
    searchInput.addEventListener("focus", () => {
      if (searchDropdown.innerHTML.trim() && searchInput.value.trim().length >= 2) {
        searchDropdown.style.display = "block";
      }
    });
  }
});

function navigateTo(viewName, subScope = null) {
  currentActiveView = viewName;
  window.location.hash = subScope ? `${viewName}?scope=${subScope}` : viewName;

  const targetNavAttr = (viewName === "recipes" && subScope === "mine") ? "my_box" : viewName;

  // Update left sidebar active classes
  document.querySelectorAll(".nav-item").forEach(item => {
    if (item.getAttribute("data-view") === targetNavAttr) {
      item.classList.add("active");
    } else {
      item.classList.remove("active");
    }
  });

  // Toggle wide layout for Planner to give maximum breathing room
  const mainLayout = document.querySelector(".main-layout");
  if (mainLayout) {
    if (viewName === "planner") {
      mainLayout.classList.add("layout-wide");
    } else {
      mainLayout.classList.remove("layout-wide");
    }
  }

  // Load View
  if (viewName === "feed") {
    loadCommunityFeedView("all");
  } else if (viewName === "stations") {
    loadStationsDirectoryView();
  } else if (viewName === "recipes") {
    loadRecipesView(subScope || "all");
  } else if (viewName === "my_box") {
    loadRecipesView("mine");
  } else if (viewName === "planner") {
    loadPlannerView();
  } else if (viewName === "admin") {
    loadAdminDashboardView();
  }
}

function openRecipeCreationMenu(event) {
  if (event) event.preventDefault();
  if (!currentUser) {
    openAuthModal("login");
    return;
  }
  openRecipeEditorModal();
}

/* ==============================================================================
   RIGHT SIDEBAR: INTERACTIVE KITCHEN TIMER
   ============================================================================== */

let sidebarTimerSeconds = 0;
let sidebarTimerInterval = null;
let sidebarTimerRunning = false;

function setSidebarTimer(minutes, label = "Timer") {
  resetSidebarTimer();
  sidebarTimerSeconds = minutes * 60;
  const labelEl = document.getElementById("sidebar-timer-label");
  if (labelEl) labelEl.textContent = label;
  updateSidebarTimerDisplay();
  startSidebarTimer();
}

function updateSidebarTimerDisplay() {
  const digitsEl = document.getElementById("sidebar-timer-digits");
  if (!digitsEl) return;
  const m = Math.floor(sidebarTimerSeconds / 60);
  const s = sidebarTimerSeconds % 60;
  digitsEl.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function toggleSidebarTimer() {
  if (sidebarTimerRunning) {
    pauseSidebarTimer();
  } else {
    if (sidebarTimerSeconds <= 0) {
      sidebarTimerSeconds = 5 * 60; // default 5m
      updateSidebarTimerDisplay();
    }
    startSidebarTimer();
  }
}

function startSidebarTimer() {
  if (sidebarTimerRunning) return;
  sidebarTimerRunning = true;
  const toggleBtn = document.getElementById("sidebar-timer-toggle-btn");
  const badge = document.getElementById("timer-status-badge");
  if (toggleBtn) {
    toggleBtn.textContent = "Pause";
    toggleBtn.classList.remove("btn-primary");
    toggleBtn.classList.add("btn-secondary");
  }
  if (badge) badge.style.display = "inline-block";

  sidebarTimerInterval = setInterval(() => {
    if (sidebarTimerSeconds > 0) {
      sidebarTimerSeconds--;
      updateSidebarTimerDisplay();
      if (sidebarTimerSeconds === 0) {
        onSidebarTimerComplete();
      }
    } else {
      pauseSidebarTimer();
    }
  }, 1000);
}

function pauseSidebarTimer() {
  sidebarTimerRunning = false;
  clearInterval(sidebarTimerInterval);
  const toggleBtn = document.getElementById("sidebar-timer-toggle-btn");
  const badge = document.getElementById("timer-status-badge");
  if (toggleBtn) {
    toggleBtn.textContent = "Resume";
    toggleBtn.classList.remove("btn-secondary");
    toggleBtn.classList.add("btn-primary");
  }
  if (badge) badge.style.display = "none";
}

function resetSidebarTimer() {
  sidebarTimerRunning = false;
  clearInterval(sidebarTimerInterval);
  sidebarTimerSeconds = 0;
  updateSidebarTimerDisplay();
  const toggleBtn = document.getElementById("sidebar-timer-toggle-btn");
  const labelEl = document.getElementById("sidebar-timer-label");
  const badge = document.getElementById("timer-status-badge");
  if (toggleBtn) {
    toggleBtn.textContent = "Start";
    toggleBtn.classList.remove("btn-secondary");
    toggleBtn.classList.add("btn-primary");
  }
  if (labelEl) labelEl.textContent = "Ready to time";
  if (badge) badge.style.display = "none";
}

function onSidebarTimerComplete() {
  pauseSidebarTimer();
  const labelEl = document.getElementById("sidebar-timer-label");
  if (labelEl) labelEl.textContent = "⏰ Time's Up!";
  showToast("⏰ Kitchen Timer Complete!", "success", 4000);
  playTimerChime();
}

function playTimerChime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
    osc.frequency.setValueAtTime(880.00, ctx.currentTime + 0.15); // A5
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.8);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.8);
  } catch (e) {
    // audio context not allowed without prior interaction
  }
}

/* ==============================================================================
   RIGHT SIDEBAR: INSTANT MEASUREMENT CONVERTER
   ============================================================================== */

const UNIT_CONVERSIONS_ML = {
  ml: 1,
  tsp: 4.92892,
  tbsp: 14.7868,
  fl_oz: 29.5735,
  cup: 236.588
};

const UNIT_CONVERSIONS_GRAMS = {
  grams: 1,
  oz: 28.3495,
  butter_stick: 113.398
};

function runUnitConversion() {
  const valInput = document.getElementById("converter-input-val");
  const fromUnitEl = document.getElementById("converter-from-unit");
  const toUnitEl = document.getElementById("converter-to-unit");
  const resultBox = document.getElementById("converter-result-box");
  if (!valInput || !fromUnitEl || !toUnitEl || !resultBox) return;

  const val = parseFloat(valInput.value);
  if (isNaN(val) || val < 0) {
    resultBox.textContent = "--";
    return;
  }

  const fromUnit = fromUnitEl.value;
  const toUnit = toUnitEl.value;

  if (fromUnit === toUnit) {
    resultBox.textContent = `${val} ${fromUnit} = ${val} ${toUnit}`;
    return;
  }

  let result = null;

  // Volume to Volume
  if (UNIT_CONVERSIONS_ML[fromUnit] && UNIT_CONVERSIONS_ML[toUnit]) {
    const inMl = val * UNIT_CONVERSIONS_ML[fromUnit];
    result = inMl / UNIT_CONVERSIONS_ML[toUnit];
  } 
  // Weight to Weight
  else if (UNIT_CONVERSIONS_GRAMS[fromUnit] && UNIT_CONVERSIONS_GRAMS[toUnit]) {
    const inG = val * UNIT_CONVERSIONS_GRAMS[fromUnit];
    result = inG / UNIT_CONVERSIONS_GRAMS[toUnit];
  }
  // Cross approximations for standard water/butter density
  else if (fromUnit === "butter_stick" && UNIT_CONVERSIONS_ML[toUnit]) {
    const inMl = val * 118.294; // 1 stick = 1/2 cup = ~118ml
    result = inMl / UNIT_CONVERSIONS_ML[toUnit];
  } else if (fromUnit === "cup" && toUnit === "grams") {
    result = val * 240; // approx liquid/flour 1 cup ~ 240g
  } else if (fromUnit === "tbsp" && toUnit === "grams") {
    result = val * 15;
  } else if (fromUnit === "tsp" && toUnit === "grams") {
    result = val * 5;
  } else if (fromUnit === "grams" && toUnit === "cup") {
    result = val / 240;
  } else if (fromUnit === "grams" && toUnit === "tbsp") {
    result = val / 15;
  } else if (fromUnit === "grams" && toUnit === "tsp") {
    result = val / 5;
  } else {
    result = val;
  }

  const formattedResult = Number.isInteger(result) ? result : parseFloat(result.toFixed(2));
  resultBox.textContent = `${val} ${fromUnit} ≈ ${formattedResult} ${toUnit}`;
}


function refreshCurrentView() {
  navigateTo(currentActiveView);
  loadRightSidebarData();
}

/* ==============================================================================
   RIGHT SIDEBAR: FEATURED CHEFS & TRENDING
   ============================================================================== */

async function loadRightSidebarData() {
  try {
    const data = await apiRequest("/api/users/featured");
    const container = document.getElementById("featured-chefs-container");
    if (!container) return;

    if (!data.chefs || data.chefs.length === 0) {
      container.innerHTML = `<p style="font-size: 0.85rem; color: var(--text-light);">No featured chefs yet</p>`;
      return;
    }

    container.innerHTML = data.chefs.map(chef => `
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem;">
        <div style="display: flex; align-items: center; gap: 0.6rem; cursor: pointer;" onclick="openUserProfile('${escapeHtml(chef.username)}')">
          <img src="${escapeHtml(chef.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" style="width: 34px; height: 34px;" />
          <div>
            <div style="font-weight: 700; font-size: 0.85rem; color: var(--text-main);">${escapeHtml(chef.display_name || chef.username)}</div>
            <div style="font-size: 0.72rem; color: var(--text-light);">${chef.recipe_count} recipes • ${chef.follower_count} followers</div>
          </div>
        </div>
        ${currentUser && currentUser.id !== chef.id ? `
          <button class="btn btn-outline btn-sm" style="padding: 2px 8px; font-size: 0.75rem;" onclick="toggleFollowUser(${chef.id}, this)">
            ${chef.is_following ? 'Following' : '+ Follow'}
          </button>
        ` : ''}
      </div>
    `).join("");
  } catch (err) {
    console.error("Error loading sidebar data:", err);
  }
}

async function toggleFollowUser(userId, btnEl) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }
  const isFollowing = btnEl.textContent.trim() === "Following";
  const method = isFollowing ? "DELETE" : "POST";

  try {
    const res = await apiRequest(`/api/users/${userId}/follow`, { method });
    btnEl.textContent = res.is_following ? "Following" : "+ Follow";
    showToast(res.is_following ? "Followed chef!" : "Unfollowed", "info", 1500);
  } catch (err) {
    showToast("Follow error: " + err.message, "error");
  }
}

/* ==============================================================================
   CHEF PROFILE VIEW
   ============================================================================== */

async function openUserProfile(username) {
  currentActiveView = "profile";
  window.location.hash = `chef/${username}`;

  const container = document.getElementById("main-content-view");
  if (!container) return;

  container.innerHTML = `<div style="text-align: center; padding: 3rem; color: var(--text-light);">Loading chef profile...</div>`;

  try {
    const data = await apiRequest(`/api/users/${encodeURIComponent(username)}`);
    const user = data.user;
    const stats = data.stats;
    const badges = data.badges || [];
    const recipes = data.recipes || [];
    const isMe = currentUser && currentUser.id === user.id;

    const badgesHtml = badges.map(b => `
      <span class="chef-badge-pill ${b.tier || 'silver'}" title="${escapeHtml(b.description)}">
        ${escapeHtml(b.icon)} ${escapeHtml(b.name)}
      </span>
    `).join("");

    const dietaryHtml = (user.dietary_preferences || []).map(d => `
      <span class="dietary-chip-mini">${escapeHtml(d)}</span>
    `).join("");

    container.innerHTML = `
      <div style="margin-bottom: 1rem;">
        <button class="btn btn-secondary btn-sm" onclick="navigateTo('feed')">← Back to Feed</button>
      </div>

      <div class="sidebar-card" style="margin-bottom: 1.5rem; padding: 1.75rem;">
        <div style="display: flex; gap: 1.25rem; align-items: center; flex-wrap: wrap;">
          <img src="${escapeHtml(user.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-lg" />
          <div style="flex: 1;">
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem; flex-wrap: wrap;">
              <h2 style="font-size: 1.5rem; margin: 0;">${escapeHtml(user.display_name || user.username)}</h2>
              ${user.is_verified ? '<span title="Verified Chef" style="font-size: 1.2rem;">⭐</span>' : ''}
              ${user.is_admin ? '<span class="badge badge-primary">Executive Chef (Admin)</span>' : ''}
            </div>
            <div style="font-size: 0.85rem; color: var(--text-light); margin-bottom: 0.5rem;">@${escapeHtml(user.username)}</div>

            <!-- Earned Badges Row -->
            ${badgesHtml ? `
              <div style="display: flex; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 0.75rem;">
                ${badgesHtml}
              </div>
            ` : ''}

            <!-- Bio -->
            <p style="font-size: 0.92rem; color: var(--text-main); margin-bottom: 0.75rem; max-width: 600px;">
              ${escapeHtml(user.bio || 'Passionate home cook exploring new flavors and culinary techniques.')}
            </p>

            <!-- Dietary Tags -->
            ${dietaryHtml ? `
              <div style="display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap; margin-bottom: 0.85rem;">
                <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600;">Diet:</span>
                ${dietaryHtml}
              </div>
            ` : ''}

            <div style="display: flex; gap: 1.5rem; font-size: 0.85rem;">
              <span><b>${stats.recipes_count}</b> Recipes</span>
              <span><b>${stats.followers_count}</b> Followers</span>
              <span><b>${stats.following_count}</b> Following</span>
            </div>
          </div>

          <div>
            ${isMe ? `
              <button class="btn btn-secondary btn-sm" onclick="openEditProfileModal()">✏️ Edit Profile</button>
            ` : `
              <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                ${currentUser ? `
                  <button class="btn ${stats.is_following ? 'btn-secondary' : 'btn-primary'} btn-sm" onclick="toggleFollowUser(${user.id}, this)">
                    ${stats.is_following ? 'Following' : '+ Follow Chef'}
                  </button>
                  <button class="btn btn-secondary btn-sm" onclick="launchDirectMessageWithUser(${user.id}, '${escapeHtml(user.username)}')">
                    ${stats.is_friend ? '💬 Whisper' : '✉️ Request Whisper'}
                  </button>
                  <button class="btn btn-outline btn-sm ${stats.is_blocked_by_me ? 'btn-danger' : ''}" style="font-size: 0.78rem;" onclick="toggleBlockChef(${user.id}, '${escapeHtml(user.username)}', ${!stats.is_blocked_by_me})">
                    ${stats.is_blocked_by_me ? 'Unblock Chef' : '🚫 Block'}
                  </button>
                ` : ''}
                ${currentUser && currentUser.is_admin === 1 ? `
                  <button class="btn btn-outline btn-sm" style="color: var(--danger); border-color: var(--danger);" onclick="adminRemoveUserFromProfile(${user.id}, '${escapeHtml(user.username)}')">
                    🛡️ Remove User (Admin)
                  </button>
                ` : ''}
              </div>
            `}
          </div>
        </div>
      </div>

      <h3 style="margin-bottom: 1rem;">Public Recipes (${recipes.length})</h3>
      <div class="recipe-grid">
        ${recipes.length === 0 ? '<div style="grid-column: 1/-1; color: var(--text-light);">No public recipes published yet.</div>' : recipes.map(r => renderRecipeCard(r)).join("")}
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div style="color: var(--danger); text-align: center; padding: 2rem;">Error loading profile: ${escapeHtml(err.message)}</div>`;
  }
}

async function toggleBlockChef(userId, username, shouldBlock) {
  const actionText = shouldBlock ? `Block @${username}? You will no longer see their posts, comments, or whispers.` : `Unblock @${username}?`;
  if (!confirm(actionText)) return;

  try {
    const method = shouldBlock ? "POST" : "DELETE";
    const res = await apiRequest(`/api/users/${userId}/block`, { method });
    showToast(res.message, "info");
    openUserProfile(username);
  } catch (err) {
    showToast("Error updating block: " + err.message, "error");
  }
}

/* ==============================================================================
   EDIT PROFILE MODAL
   ============================================================================== */

const DEFAULT_AVATAR = "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100";
let isAvatarUploading = false;

function openEditProfileModal() {
  if (!currentUser) return;
  const modal = document.getElementById("profile-modal");
  if (!modal) return;

  const currentAvatar = currentUser.avatar_url || "";
  document.getElementById("profile-display-input").value = currentUser.display_name || "";
  document.getElementById("profile-avatar-input").value = currentAvatar;
  document.getElementById("profile-bio-input").value = currentUser.bio || "";

  // Set dietary preferences checkboxes
  const currentDietary = currentUser.dietary_preferences || [];
  document.querySelectorAll(".profile-dietary-checkbox").forEach(cb => {
    cb.checked = currentDietary.includes(cb.value);
  });

  const preview = document.getElementById("profile-avatar-preview");
  if (preview) {
    preview.src = currentAvatar || DEFAULT_AVATAR;
  }

  const removeBtn = document.getElementById("profile-avatar-remove-btn");
  if (removeBtn) {
    removeBtn.style.display = currentAvatar ? "inline-block" : "none";
  }

  const spinner = document.getElementById("profile-avatar-uploading-spinner");
  if (spinner) spinner.style.display = "none";

  const fileInput = document.getElementById("profile-avatar-file-input");
  if (fileInput) fileInput.value = "";

  modal.classList.add("show");
}

function closeEditProfileModal() {
  const modal = document.getElementById("profile-modal");
  if (modal) modal.classList.remove("show");
}

function handleProfileAvatarUrlInput(val) {
  let trimmed = (val || "").trim();
  const preview = document.getElementById("profile-avatar-preview");
  const removeBtn = document.getElementById("profile-avatar-remove-btn");

  if (!trimmed) {
    if (preview) preview.src = DEFAULT_AVATAR;
    if (removeBtn) removeBtn.style.display = "none";
    return;
  }

  if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://") && !trimmed.startsWith("/uploads/") && !trimmed.startsWith("data:")) {
    trimmed = "https://" + trimmed;
  }

  if (preview) {
    preview.src = trimmed;
  }
  if (removeBtn) {
    removeBtn.style.display = "inline-block";
  }
}

function removeProfileAvatar() {
  const avatarInput = document.getElementById("profile-avatar-input");
  const preview = document.getElementById("profile-avatar-preview");
  const removeBtn = document.getElementById("profile-avatar-remove-btn");
  const fileInput = document.getElementById("profile-avatar-file-input");

  if (avatarInput) avatarInput.value = "";
  if (fileInput) fileInput.value = "";
  if (preview) preview.src = DEFAULT_AVATAR;
  if (removeBtn) removeBtn.style.display = "none";

  showToast("Profile photo removed. Click Update Profile to save.", "info");
}

async function handleProfileAvatarFileSelect(input) {
  const file = input?.files?.[0];
  if (!file) return;

  const preview = document.getElementById("profile-avatar-preview");
  const spinner = document.getElementById("profile-avatar-uploading-spinner");
  const removeBtn = document.getElementById("profile-avatar-remove-btn");
  const saveBtn = document.getElementById("profile-save-btn");
  const avatarInput = document.getElementById("profile-avatar-input");

  try {
    isAvatarUploading = true;
    if (saveBtn) saveBtn.disabled = true;
    if (spinner) spinner.style.display = "flex";

    if (preview) {
      preview.src = URL.createObjectURL(file);
    }

    showToast("Uploading profile photo...", "info", 1500);

    let uploadBlob = file;
    try {
      if (typeof downsampleImageFile === "function") {
        uploadBlob = await downsampleImageFile(file, 1280, 1280);
      }
    } catch (downsampleErr) {
      uploadBlob = file;
    }

    const formData = new FormData();
    formData.append("image", uploadBlob, file.name || "avatar.jpg");

    const res = await apiRequest("/api/upload", {
      method: "POST",
      body: formData
    });

    if (res && res.url) {
      if (avatarInput) avatarInput.value = res.url;
      if (preview) preview.src = res.url;
      if (removeBtn) removeBtn.style.display = "inline-block";
      showToast("Profile photo uploaded! Click Update Profile to save.", "success");
    }
  } catch (err) {
    showToast("Photo upload failed: " + err.message, "error");
    if (preview) preview.src = currentUser.avatar_url || DEFAULT_AVATAR;
  } finally {
    isAvatarUploading = false;
    if (spinner) spinner.style.display = "none";
    if (saveBtn) saveBtn.disabled = false;
  }
}

async function handleProfileUpdateSubmit(e) {
  e.preventDefault();
  if (isAvatarUploading) {
    showToast("Please wait for your photo to finish uploading...", "info");
    return;
  }

  const display_name = document.getElementById("profile-display-input").value.trim();
  let avatar_url = document.getElementById("profile-avatar-input").value.trim();
  const bio = document.getElementById("profile-bio-input").value.trim();

  // Collect dietary preferences
  const dietary_preferences = [];
  document.querySelectorAll(".profile-dietary-checkbox:checked").forEach(cb => {
    dietary_preferences.push(cb.value);
  });

  if (avatar_url && !avatar_url.startsWith("http://") && !avatar_url.startsWith("https://") && !avatar_url.startsWith("/uploads/") && !avatar_url.startsWith("data:")) {
    avatar_url = "https://" + avatar_url;
  }

  try {
    const data = await apiRequest("/api/users/profile", {
      method: "PUT",
      body: JSON.stringify({ display_name, avatar_url, bio, dietary_preferences })
    });
    showToast(data.message || "Profile updated successfully!", "success");
    closeEditProfileModal();

    if (currentUser) {
      currentUser.display_name = display_name;
      currentUser.avatar_url = avatar_url;
      currentUser.bio = bio;
      currentUser.dietary_preferences = dietary_preferences;
    }

    openUserProfile(currentUser.username);
  } catch (err) {
    showToast("Update failed: " + err.message, "error");
  }
}



async function adminRemoveUserFromProfile(userId, username) {
  if (!confirm(`Are you sure you want to PERMANENTLY REMOVE @${username}?\n\nThis will immediately delete their account, profile, recipes, posts, and comments.`)) {
    return;
  }

  try {
    const res = await apiRequest(`/api/admin/users/${userId}`, { method: "DELETE" });
    showToast(res.message || `User @${username} removed`, "success");
    navigateTo("feed");
  } catch (err) {
    showToast("Error deleting user: " + err.message, "error");
  }
}

function debounce(func, wait) {
  let timeout;
  return function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

/* ==============================================================================
   GLOBAL SEARCH RENDERER & ACTION HANDLER
   ============================================================================== */

function renderGlobalSearchDropdown(data, query) {
  const container = document.getElementById("search-dropdown-results");
  if (!container) return;

  const recipes = data.recipes || [];
  const chefs = data.chefs || [];
  const stations = data.stations || [];
  const posts = data.posts || [];

  const totalResults = recipes.length + chefs.length + stations.length + posts.length;

  if (totalResults === 0) {
    container.innerHTML = `
      <div class="search-empty-state">
        <p>No results found for "<b>${escapeHtml(query)}</b>"</p>
        <div style="margin-top: 0.35rem; font-size: 0.8rem; color: var(--text-light);">Try searching for recipes, dishes, ingredients, chefs, or stations</div>
      </div>
    `;
    container.style.display = "block";
    return;
  }

  let html = "";
  const isUserSpecificSearch = query.trim().startsWith("@");

  const renderChefsSection = () => {
    if (chefs.length === 0) return "";
    let s = `<div class="search-section-header">Chefs & Cooks (${chefs.length})</div>`;
    chefs.forEach(c => {
      s += `
        <div class="search-result-item" onclick="selectSearchResult('chef', '${escapeHtml(c.username)}')">
          <img src="${escapeHtml(c.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="search-result-thumb" style="border-radius: 50%;" alt="${escapeHtml(c.username)}" />
          <div class="search-result-info">
            <span class="search-result-title">${escapeHtml(c.display_name || c.username)}</span>
            <span class="search-result-subtitle">@${escapeHtml(c.username)} • ${c.recipe_count} recipes • ${c.follower_count} followers</span>
          </div>
          ${c.is_following ? '<span class="badge" style="background:var(--bg-surface-subtle); color:var(--text-light); font-size:0.7rem;">Following</span>' : ''}
        </div>
      `;
    });
    return s;
  };

  const renderRecipesSection = () => {
    if (recipes.length === 0) return "";
    let s = `<div class="search-section-header">Recipes (${recipes.length})</div>`;
    recipes.forEach(r => {
      const timeStr = r.cook_time_min ? `${r.cook_time_min}m cook` : (r.prep_time_min ? `${r.prep_time_min}m prep` : "");
      const meta = [r.cuisine, timeStr, `by ${r.display_name || r.username}`].filter(Boolean).join(" • ");
      s += `
        <div class="search-result-item" onclick="selectSearchResult('recipe', ${r.id})">
          <img src="${escapeHtml(r.image_url || 'https://images.unsplash.com/photo-1495521821757-a1efb6729352?w=100')}" class="search-result-thumb" alt="${escapeHtml(r.title)}" />
          <div class="search-result-info">
            <span class="search-result-title">${escapeHtml(r.title)}</span>
            <span class="search-result-subtitle">${escapeHtml(meta)}</span>
          </div>
        </div>
      `;
    });
    return s;
  };

  const renderStationsSection = () => {
    if (stations.length === 0) return "";
    let s = `<div class="search-section-header">Kitchen Stations (${stations.length})</div>`;
    stations.forEach(st => {
      s += `
        <div class="search-result-item" onclick="selectSearchResult('station', '${escapeHtml(st.slug)}')">
          <div class="search-result-icon">${escapeHtml(st.icon || '🍳')}</div>
          <div class="search-result-info">
            <span class="search-result-title">${escapeHtml(st.name)}</span>
            <span class="search-result-subtitle">${st.member_count || 0} cooks joined</span>
          </div>
        </div>
      `;
    });
    return s;
  };

  const renderPostsSection = () => {
    if (posts.length === 0) return "";
    let s = `<div class="search-section-header">Community Discussions (${posts.length})</div>`;
    posts.forEach(p => {
      const typeLabel = p.post_type === 'question' ? '❓ Question' : (p.post_type === 'showcase' ? '📸 Showcase' : '💬 Post');
      s += `
        <div class="search-result-item" onclick="selectSearchResult('feed', ${p.id})">
          <img src="${escapeHtml(p.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="search-result-thumb" style="border-radius: 50%;" alt="${escapeHtml(p.username)}" />
          <div class="search-result-info">
            <span class="search-result-title">${escapeHtml(p.content.substring(0, 50))}${p.content.length > 50 ? '...' : ''}</span>
            <span class="search-result-subtitle">${typeLabel} by @${escapeHtml(p.username)}</span>
          </div>
        </div>
      `;
    });
    return s;
  };

  if (isUserSpecificSearch) {
    html += renderChefsSection();
    html += renderRecipesSection();
    html += renderStationsSection();
    html += renderPostsSection();
  } else {
    html += renderRecipesSection();
    html += renderChefsSection();
    html += renderStationsSection();
    html += renderPostsSection();
  }

  container.innerHTML = html;
  container.style.display = "block";
}

function selectSearchResult(type, idOrSlug) {
  const searchDropdown = document.getElementById("search-dropdown-results");
  if (searchDropdown) searchDropdown.style.display = "none";

  if (type === "recipe") {
    viewRecipeDetail(idOrSlug);
  } else if (type === "chef") {
    openUserProfile(idOrSlug);
  } else if (type === "station") {
    navigateToStation(idOrSlug);
  } else if (type === "feed") {
    navigateTo("feed");
  }
}

