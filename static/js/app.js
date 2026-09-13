/* ==============================================================================
   COOKED - Main App Router & View Controller
   ============================================================================== */

let currentActiveView = "feed"; // 'feed', 'recipes', 'planner', 'profile'

document.addEventListener("DOMContentLoaded", async () => {
  // Initialize Auth
  await checkAuthStatus();

  // Load Featured Chefs & Right Sidebar Content
  loadRightSidebarData();

  // Route to initial view based on URL hash or default to feed
  const hash = window.location.hash.replace("#", "");
  if (hash.startsWith("recipe/")) {
    const id = hash.split("/")[1];
    viewRecipeDetail(parseInt(id));
  } else if (hash.startsWith("chef/")) {
    const user = hash.split("/")[1];
    openUserProfile(user);
  } else if (hash.startsWith("station/")) {
    const slug = hash.split("/")[1];
    navigateToStation(slug);
  } else if (["stations", "recipes", "planner", "admin"].includes(hash)) {
    navigateTo(hash);
  } else {
    navigateTo("feed");
  }

  // Setup Global Search Input
  const searchInput = document.getElementById("global-search-input");
  if (searchInput) {
    searchInput.addEventListener("input", debounce((e) => {
      const q = e.target.value.trim();
      if (currentActiveView === "recipes") {
        fetchAndRenderRecipes(q);
      } else if (currentActiveView === "feed") {
        fetchAndRenderPosts(q);
      } else if (currentActiveView === "stations") {
        fetchAndRenderStations(q);
      }
    }, 300));
  }
});

function navigateTo(viewName) {
  currentActiveView = viewName;
  window.location.hash = viewName;

  // Update left sidebar active classes
  document.querySelectorAll(".nav-item").forEach(item => {
    if (item.getAttribute("data-view") === viewName) {
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
    loadRecipesView("all");
  } else if (viewName === "planner") {
    loadPlannerView();
  } else if (viewName === "admin") {
    loadAdminDashboardView();
  }
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
    const recipes = data.recipes || [];
    const isMe = currentUser && currentUser.id === user.id;

    container.innerHTML = `
      <div style="margin-bottom: 1rem;">
        <button class="btn btn-secondary btn-sm" onclick="navigateTo('feed')">← Back to Feed</button>
      </div>

      <div class="sidebar-card" style="margin-bottom: 1.5rem; padding: 1.75rem;">
        <div style="display: flex; gap: 1.25rem; align-items: center; flex-wrap: wrap;">
          <img src="${escapeHtml(user.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-lg" />
          <div style="flex: 1;">
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
              <h2 style="font-size: 1.5rem;">${escapeHtml(user.display_name || user.username)}</h2>
              ${user.is_admin ? '<span class="badge badge-primary">Executive Chef (Admin)</span>' : ''}
            </div>
            <div style="font-size: 0.85rem; color: var(--text-light); margin-bottom: 0.75rem;">@${escapeHtml(user.username)}</div>
            <p style="font-size: 0.92rem; color: var(--text-main); margin-bottom: 1rem; max-width: 600px;">
              ${escapeHtml(user.bio || 'Passionate home cook exploring new flavors and culinary techniques.')}
            </p>

            <div style="display: flex; gap: 1.5rem; font-size: 0.85rem;">
              <span><b>${stats.recipes_count}</b> Recipes</span>
              <span><b>${stats.followers_count}</b> Followers</span>
              <span><b>${stats.following_count}</b> Following</span>
            </div>
          </div>

          <div>
            ${isMe ? `
              <button class="btn btn-secondary btn-sm" onclick="openEditProfileModal()">✏️ Edit Profile</button>
            ` : (currentUser ? `
              <button class="btn ${stats.is_following ? 'btn-secondary' : 'btn-primary'} btn-sm" onclick="toggleFollowUser(${user.id}, this)">
                ${stats.is_following ? 'Following' : '+ Follow Chef'}
              </button>
            ` : '')}
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

/* ==============================================================================
   EDIT PROFILE MODAL
   ============================================================================== */

function openEditProfileModal() {
  if (!currentUser) return;
  const modal = document.getElementById("profile-modal");
  if (!modal) return;

  document.getElementById("profile-display-input").value = currentUser.display_name || "";
  document.getElementById("profile-avatar-input").value = currentUser.avatar_url || "";
  document.getElementById("profile-bio-input").value = currentUser.bio || "";

  modal.classList.add("show");
}

function closeEditProfileModal() {
  const modal = document.getElementById("profile-modal");
  if (modal) modal.classList.remove("show");
}

async function handleProfileUpdateSubmit(e) {
  e.preventDefault();
  const display_name = document.getElementById("profile-display-input").value.trim();
  const avatar_url = document.getElementById("profile-avatar-input").value.trim();
  const bio = document.getElementById("profile-bio-input").value.trim();

  try {
    const data = await apiRequest("/api/users/profile", {
      method: "PUT",
      body: JSON.stringify({ display_name, avatar_url, bio })
    });
    showToast(data.message, "success");
    closeEditProfileModal();
    await checkAuthStatus();
    openUserProfile(currentUser.username);
  } catch (err) {
    showToast("Error updating profile: " + err.message, "error");
  }
}

function debounce(func, wait) {
  let timeout;
  return function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}
