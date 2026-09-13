/* ==============================================================================
   COOKED - Kitchen Stations (Culinary Sub-Communities) Module
   ============================================================================== */

let currentStationSlug = null;
let currentStationFilter = "all";

/**
 * Load and render the full Kitchen Stations Directory.
 */
async function loadStationsDirectoryView(searchQuery = "") {
  const container = document.getElementById("main-content-view");
  if (!container) return;

  container.innerHTML = `
    <div class="stations-directory-header">
      <div class="stations-header-text">
        <div class="stations-badge-title">
          <span class="pulse-dot"></span>
          <span>Culinary Sub-Communities</span>
        </div>
        <h2>🍳 Kitchen Stations</h2>
        <p>Specialized workstations built around culinary crafts, regional traditions, and cooking techniques. Clock in to join the brigade!</p>
      </div>
      <div class="stations-header-actions">
        <div class="search-input-wrap">
          <input type="text" id="stations-search-input" class="form-control" placeholder="Search stations..." value="${escapeHtml(searchQuery)}" oninput="handleStationsSearch(event)" />
        </div>
        <button class="btn btn-primary" onclick="openCreateStationModal()">
          <span>+ Open Station</span>
        </button>
      </div>
    </div>

    <!-- Stations Grid Container -->
    <div id="stations-grid-container" class="stations-grid">
      <div style="grid-column: 1 / -1; text-align: center; padding: 3rem; color: var(--text-light);">
        Loading kitchen stations...
      </div>
    </div>
  `;

  await fetchAndRenderStations(searchQuery);
}

/**
 * Fetch and render station cards in the directory.
 */
async function fetchAndRenderStations(searchQuery = "") {
  const container = document.getElementById("stations-grid-container");
  if (!container) return;

  try {
    let url = "/api/stations";
    if (searchQuery) url += `?q=${encodeURIComponent(searchQuery)}`;
    const data = await apiRequest(url);

    if (!data.stations || data.stations.length === 0) {
      container.innerHTML = `
        <div class="empty-stations-state">
          <span style="font-size: 2.5rem; display: block; margin-bottom: 0.5rem;">🍳</span>
          <h3>No Kitchen Stations Found</h3>
          <p>Try a different keyword or be the first chef to open a new station!</p>
          <button class="btn btn-primary btn-sm" style="margin-top: 1rem;" onclick="openCreateStationModal()">+ Open New Station</button>
        </div>
      `;
      return;
    }

    container.innerHTML = data.stations.map(station => renderStationCard(station)).join("");
  } catch (err) {
    container.innerHTML = `
      <div class="empty-stations-state">
        <span style="font-size: 2rem; color: var(--danger);">⚠️</span>
        <p>Error loading stations: ${escapeHtml(err.message)}</p>
      </div>
    `;
  }
}

function handleStationsSearch(e) {
  const q = e.target.value.trim();
  if (window._stationSearchTimeout) clearTimeout(window._stationSearchTimeout);
  window._stationSearchTimeout = setTimeout(() => {
    fetchAndRenderStations(q);
  }, 300);
}

/**
 * Render an individual Station Card.
 */
function renderStationCard(station) {
  const isMember = Boolean(station.is_member);
  const bannerBg = station.banner_url
    ? `background-image: linear-gradient(180deg, rgba(0,0,0,0.2) 0%, rgba(0,0,0,0.75) 100%), url('${escapeHtml(station.banner_url)}');`
    : `background: linear-gradient(135deg, var(--primary), #1a3a2a);`;

  return `
    <div class="station-card" onclick="navigateToStation('${escapeHtml(station.slug)}')">
      <div class="station-card-banner" style="${bannerBg}">
        <div class="station-card-icon">${escapeHtml(station.icon || '🍳')}</div>
        <div class="station-card-pill">station/${escapeHtml(station.slug)}</div>
      </div>
      
      <div class="station-card-body">
        <h3 class="station-card-title">${escapeHtml(station.name)}</h3>
        <p class="station-card-desc">${escapeHtml(station.description)}</p>
        
        <div class="station-card-footer">
          <div class="station-stats">
            <span title="Chefs Clocked In">👥 <b id="stat-members-${station.slug}">${station.member_count || 0}</b></span>
            <span title="Station Posts">📝 <b>${station.post_count || 0}</b></span>
          </div>
          <button class="btn btn-sm ${isMember ? 'btn-station-active' : 'btn-station-clockin'}" 
                  id="station-btn-${station.slug}"
                  onclick="event.stopPropagation(); toggleJoinStation('${escapeHtml(station.slug)}', this)">
            ${isMember ? 'Clocked In ✓' : 'Clock In'}
          </button>
        </div>
      </div>
    </div>
  `;
}

/**
 * Navigate to a specific station detail view.
 */
function navigateToStation(slug) {
  currentStationSlug = slug;
  window.location.hash = `station/${slug}`;
  // Update nav highlights
  document.querySelectorAll(".nav-item").forEach(item => {
    if (item.getAttribute("data-view") === "stations") {
      item.classList.add("active");
    } else {
      item.classList.remove("active");
    }
  });
  loadStationDetailView(slug, "all");
}

/**
 * Load and render a specific Station Detail View (Hero, Rules, Members, and Filtered Feed).
 */
async function loadStationDetailView(slug, filter = "all") {
  currentStationSlug = slug;
  currentStationFilter = filter;
  const container = document.getElementById("main-content-view");
  if (!container) return;

  container.innerHTML = `
    <div style="text-align: center; padding: 3rem; color: var(--text-light);">
      Loading station workstation...
    </div>
  `;

  try {
    const [stationRes, postsRes, leaderboardRes] = await Promise.all([
      apiRequest(`/api/stations/${encodeURIComponent(slug)}`),
      apiRequest(`/api/posts?station=${encodeURIComponent(slug)}&type=${encodeURIComponent(filter)}`),
      apiRequest(`/api/stations/${encodeURIComponent(slug)}/leaderboard`).catch(() => ({ lead_cooks: [] }))
    ]);

    const station = stationRes.station;
    const posts = postsRes.posts || [];
    const isMember = Boolean(station.is_member);
    const leadCooks = leaderboardRes?.lead_cooks || [];

    const bannerStyle = station.banner_url
      ? `background-image: linear-gradient(180deg, rgba(15,19,17,0.35) 0%, rgba(15,19,17,0.9) 100%), url('${escapeHtml(station.banner_url)}');`
      : `background: linear-gradient(135deg, #1c3d2d, #0f1311);`;

    container.innerHTML = `
      <!-- Station Breadcrumb / Back -->
      <div style="margin-bottom: 0.75rem;">
        <button class="btn btn-secondary btn-sm" onclick="navigateTo('stations')" style="gap: 0.35rem;">
          <span>← Back to Kitchen Stations</span>
        </button>
      </div>

      <!-- Station Hero Header -->
      <div class="station-hero" style="${bannerStyle}">
        <div class="station-hero-content">
          <div class="station-hero-top">
            <div class="station-hero-icon">${escapeHtml(station.icon || '🍳')}</div>
            <div class="station-hero-info">
              <div class="station-slug-tag">station/${escapeHtml(station.slug)}</div>
              <h1 class="station-hero-title">${escapeHtml(station.name)}</h1>
              <p class="station-hero-desc">${escapeHtml(station.description)}</p>
            </div>
          </div>

          <div class="station-hero-actions">
            <div class="station-hero-stats">
              <div class="hero-stat-box">
                <span class="hero-stat-val" id="detail-member-count">${station.member_count || 0}</span>
                <span class="hero-stat-label">Chefs Clocked In</span>
              </div>
              <div class="hero-stat-box">
                <span class="hero-stat-val">${station.post_count || 0}</span>
                <span class="hero-stat-label">Dishes & Questions</span>
              </div>
              ${station.user_role ? `
                <div class="hero-stat-box role-stat-box">
                  <span class="hero-stat-val" style="color: var(--secondary); font-size: 0.95rem;">${station.user_role === 'lead_cook' ? '⭐ Lead Cook' : '👨‍🍳 Line Chef'}</span>
                  <span class="hero-stat-label">Your Station Rank</span>
                </div>
              ` : ''}
            </div>

            <div style="display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap;">
              <button class="btn ${isMember ? 'btn-station-active' : 'btn-primary'}" 
                      id="detail-clockin-btn"
                      onclick="toggleJoinStation('${escapeHtml(station.slug)}', this, true)">
                ${isMember ? 'Clocked In ✓' : 'Clock In to Station'}
              </button>
              <button class="btn btn-secondary" onclick="openCreateModal('post', ${station.id})">
                <span>+ Post to Station</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Station Main 2-Column Workstation Grid -->
      <div class="station-workstation-grid">
        
        <!-- Left Column: Leaderboard, Rules & Brigade -->
        <aside class="station-sidebar-col">
          
          <!-- Station Leaderboard -->
          <div class="station-sidebar-card">
            <div class="station-sidebar-header">
              <span>🏆</span>
              <h4>Station Leaderboard</h4>
            </div>
            <div class="station-leaderboard-list">
              ${renderStationLeaderboard(leadCooks)}
            </div>
          </div>

          <!-- Station Rules Box -->
          <div class="station-sidebar-card">
            <div class="station-sidebar-header">
              <span>📜</span>
              <h4>Station Standards & Rules</h4>
            </div>
            <div class="station-rules-content">
              ${station.rules_text ? formatStationRules(station.rules_text) : '<p style="color: var(--text-light); font-size: 0.85rem;">No custom rules specified for this station.</p>'}
            </div>
          </div>

          <!-- Station Brigade / Lead Cooks -->
          <div class="station-sidebar-card">
            <div class="station-sidebar-header">
              <span>👨‍🍳</span>
              <h4>Station Brigade</h4>
            </div>
            <div class="station-brigade-list">
              ${renderBrigadeList(station.members_sample || [])}
            </div>
          </div>

        </aside>

        <!-- Right Column: Station Posts Stream -->
        <div class="station-feed-col">
          
          <!-- Filter Tabs for this Station -->
          <div class="feed-filter-bar" style="margin-bottom: 1rem;">
            <button class="filter-chip ${filter === 'all' ? 'active' : ''}" onclick="loadStationDetailView('${escapeHtml(slug)}', 'all')">🔥 Station Feed</button>
            <button class="filter-chip ${filter === 'question' ? 'active' : ''}" onclick="loadStationDetailView('${escapeHtml(slug)}', 'question')">❓ Questions</button>
            <button class="filter-chip ${filter === 'showcase' ? 'active' : ''}" onclick="loadStationDetailView('${escapeHtml(slug)}', 'showcase')">📸 Showcases</button>
          </div>

          <!-- Quick Post Banner inside Station -->
          <div class="create-post-card" style="margin-bottom: 1.25rem;">
            <div class="create-post-header">
              <img src="${escapeHtml(currentUser?.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" />
              <input type="text" class="form-control" style="border-radius: var(--radius-full); cursor: pointer;" 
                     placeholder="Post a tip, crumb shot, or question to ${escapeHtml(station.name)}..." 
                     onclick="openCreateModal('post', ${station.id})" readonly />
            </div>
          </div>

          <!-- Station Posts Container -->
          <div id="station-posts-stream">
            ${posts.length > 0 
              ? posts.map(post => renderPostCard(post)).join("")
              : `
                <div class="empty-station-feed">
                  <span style="font-size: 2.2rem; display: block; margin-bottom: 0.5rem;">${escapeHtml(station.icon || '🍳')}</span>
                  <h3>No posts in ${escapeHtml(station.name)} yet</h3>
                  <p>Be the first chef to fire up this station with a dish or question!</p>
                  <button class="btn btn-primary btn-sm" style="margin-top: 0.75rem;" onclick="openCreateModal('post', ${station.id})">
                    + Fire First Post
                  </button>
                </div>
              `
            }
          </div>

        </div>

      </div>
    `;
  } catch (err) {
    container.innerHTML = `
      <div class="empty-stations-state">
        <span style="font-size: 2rem; color: var(--danger);">⚠️</span>
        <h3>Could not load Kitchen Station</h3>
        <p>${escapeHtml(err.message)}</p>
        <button class="btn btn-secondary btn-sm" onclick="navigateTo('stations')">Back to Stations</button>
      </div>
    `;
  }
}

function formatStationRules(rulesText) {
  const lines = rulesText.split("\n").filter(l => l.trim().length > 0);
  if (lines.length === 0) return `<p style="font-size: 0.85rem; color: var(--text-light);">Standard kitchen etiquette applies.</p>`;

  return `
    <ul class="station-rules-list">
      ${lines.map(line => `<li>${escapeHtml(line)}</li>`).join("")}
    </ul>
  `;
}

function renderBrigadeList(members) {
  if (!members || members.length === 0) {
    return `<p style="font-size: 0.85rem; color: var(--text-light);">No active brigade members yet.</p>`;
  }

  return members.map(m => `
    <div class="brigade-member-item" onclick="openUserProfile('${escapeHtml(m.username)}')">
      <img src="${escapeHtml(m.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" style="width: 32px; height: 32px;" />
      <div class="brigade-member-info">
        <div class="brigade-member-name">
          ${escapeHtml(m.display_name || m.username)}
          ${m.role === 'lead_cook' ? '<span class="lead-badge" title="Station Lead Cook">⭐ Lead</span>' : ''}
        </div>
        <div class="brigade-member-user">@${escapeHtml(m.username)}</div>
      </div>
    </div>
  `).join("");
}

function renderStationLeaderboard(leadCooks) {
  if (!leadCooks || leadCooks.length === 0) {
    return `<p style="font-size: 0.85rem; color: var(--text-light); text-align: center; padding: 0.75rem 0.25rem;">No station activity yet. Clock in and share your first dish!</p>`;
  }

  return leadCooks.map((chef, idx) => {
    const rankClass = idx === 0 ? 'rank-1' : (idx === 1 ? 'rank-2' : (idx === 2 ? 'rank-3' : ''));
    const rankBadge = idx === 0 ? '🥇' : (idx === 1 ? '🥈' : (idx === 2 ? '🥉' : `#${idx + 1}`));
    return `
      <div class="leaderboard-item" onclick="openUserProfile('${escapeHtml(chef.username)}')">
        <span class="leaderboard-rank-badge ${rankClass}">${rankBadge}</span>
        <img src="${escapeHtml(chef.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" style="width: 28px; height: 28px;" />
        <div style="min-width: 0; flex: 1;">
          <div style="font-weight: 700; font-size: 0.82rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            ${escapeHtml(chef.display_name || chef.username)}
          </div>
          <div style="font-size: 0.72rem; color: var(--text-light);">@${escapeHtml(chef.username)}</div>
        </div>
        <div class="leaderboard-stats">
          <div>❤️ <b>${chef.likes_received || 0}</b></div>
          <div>📝 ${chef.post_count || 0}</div>
        </div>
      </div>
    `;
  }).join("");
}

/**
 * Toggle Clock In / Clock Out of a station.
 */
async function toggleJoinStation(slug, btnEl, isDetailView = false) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }

  try {
    const res = await apiRequest(`/api/stations/${encodeURIComponent(slug)}/join`, {
      method: "POST"
    });

    const isMember = res.is_member;
    showToast(res.message, isMember ? "success" : "info");

    // Update Directory Button state if present
    const dirBtn = document.getElementById(`station-btn-${slug}`);
    if (dirBtn) {
      if (isMember) {
        dirBtn.className = "btn btn-sm btn-station-active";
        dirBtn.textContent = "Clocked In ✓";
      } else {
        dirBtn.className = "btn btn-sm btn-station-clockin";
        dirBtn.textContent = "Clock In";
      }
    }

    // Update Directory member count stat if present
    const memberStat = document.getElementById(`stat-members-${slug}`);
    if (memberStat) {
      memberStat.textContent = res.member_count;
    }

    // Update Detail View Button state & Stat if present
    const detailBtn = document.getElementById("detail-clockin-btn");
    if (detailBtn) {
      if (isMember) {
        detailBtn.className = "btn btn-station-active";
        detailBtn.textContent = "Clocked In ✓";
      } else {
        detailBtn.className = "btn btn-primary";
        detailBtn.textContent = "Clock In to Station";
      }
    }

    const detailCount = document.getElementById("detail-member-count");
    if (detailCount) {
      detailCount.textContent = res.member_count;
    }
  } catch (err) {
    showToast("Error updating station membership: " + err.message, "error");
  }
}

/**
 * Open Create Station Modal
 */
function openCreateStationModal() {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }

  const modal = document.getElementById("create-station-modal");
  if (!modal) return;

  document.getElementById("station-create-name").value = "";
  document.getElementById("station-create-desc").value = "";
  document.getElementById("station-create-icon").value = "🍳";
  document.getElementById("station-create-banner").value = "";
  document.getElementById("station-create-rules").value = "";

  modal.classList.add("show");
}

function closeCreateStationModal() {
  const modal = document.getElementById("create-station-modal");
  if (modal) modal.classList.remove("show");
}

/**
 * Handle new Station creation submit
 */
async function handleStationCreateSubmit(e) {
  e.preventDefault();

  const name = document.getElementById("station-create-name").value.trim();
  const description = document.getElementById("station-create-desc").value.trim();
  const icon = document.getElementById("station-create-icon").value.trim() || "🍳";
  const banner_url = document.getElementById("station-create-banner").value.trim();
  const rules_text = document.getElementById("station-create-rules").value.trim();

  if (!name || !description) {
    showToast("Station name and description are required", "error");
    return;
  }

  try {
    const res = await apiRequest("/api/stations", {
      method: "POST",
      body: JSON.stringify({
        name,
        description,
        icon,
        banner_url,
        rules_text
      })
    });

    showToast(res.message || "Kitchen Station opened!", "success");
    closeCreateStationModal();
    navigateToStation(res.station.slug);
  } catch (err) {
    showToast("Failed to open station: " + err.message, "error");
  }
}
