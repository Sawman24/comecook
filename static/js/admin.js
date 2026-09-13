/* ==============================================================================
   COOKED - Executive Kitchen Moderation & Admin Command Center
   ============================================================================== */

let currentAdminReports = [];
let adminUserSearchDebounce = null;

async function loadAdminDashboardView() {
  if (!currentUser || currentUser.is_admin !== 1) {
    const container = document.getElementById("main-content-view");
    container.innerHTML = `
      <div style="text-align: center; padding: 3.5rem 1.5rem; background: var(--bg-surface); border-radius: var(--radius-lg); border: 1px solid var(--border-color);">
        <span style="font-size: 3rem; display: block; margin-bottom: 0.75rem;">🔒</span>
        <h2>Executive Access Required</h2>
        <p style="color: var(--text-muted); margin: 0.5rem 0 1.25rem 0;">You must be an Executive Chef / Admin to access the Moderation Command Center.</p>
        <button class="btn btn-primary" onclick="navigateTo('feed')">Return to Community</button>
      </div>
    `;
    return;
  }

  const container = document.getElementById("main-content-view");
  if (!container) return;

  container.innerHTML = `
    <div style="margin-bottom: 1.5rem;">
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1.25rem;">
        <div>
          <h2 style="font-size: 1.5rem; margin-bottom: 0.25rem; display: flex; align-items: center; gap: 0.5rem;">
            <span>🛡️</span> Kitchen Command & Moderation Center
          </h2>
          <p style="color: var(--text-muted); font-size: 0.88rem; margin: 0;">
            Platform health, live metrics, user administration, and community moderation
          </p>
        </div>
        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
          <button class="btn btn-outline btn-sm" style="color: #ea580c; border-color: #ea580c;" onclick="purgeStressTestData()">
            🧹 Purge Stress Test Data
          </button>
          <button class="btn btn-outline btn-sm" style="color: var(--danger); border-color: var(--danger);" onclick="purgeOffensiveAccounts()">
            🛡️ Purge Offensive Accounts
          </button>
          <button class="btn btn-secondary btn-sm" onclick="loadAdminDashboardView()">
            🔄 Refresh Queue
          </button>
        </div>
      </div>

      <!-- Platform Overview Stats Cards -->
      <div id="admin-stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
        <div class="card" style="padding: 1.25rem; text-align: center; background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: var(--radius-md);">
          <div style="font-size: 2rem;">👨‍🍳</div>
          <div id="stat-admin-users" style="font-size: 1.6rem; font-weight: 800; color: var(--text-main); margin-top: 0.25rem;">--</div>
          <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;">Registered Chefs</div>
        </div>
        <div class="card" style="padding: 1.25rem; text-align: center; background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: var(--radius-md);">
          <div style="font-size: 2rem;">📖</div>
          <div id="stat-admin-recipes" style="font-size: 1.6rem; font-weight: 800; color: var(--primary); margin-top: 0.25rem;">--</div>
          <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;">Active Recipes</div>
        </div>
        <div class="card" style="padding: 1.25rem; text-align: center; background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: var(--radius-md);">
          <div style="font-size: 2rem;">💬</div>
          <div id="stat-admin-posts" style="font-size: 1.6rem; font-weight: 800; color: var(--accent); margin-top: 0.25rem;">--</div>
          <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;">Community Posts</div>
        </div>
        <div class="card" style="padding: 1.25rem; text-align: center; background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: var(--radius-md);">
          <div style="font-size: 2rem;">🚩</div>
          <div id="stat-admin-reports" style="font-size: 1.6rem; font-weight: 800; color: var(--danger); margin-top: 0.25rem;">--</div>
          <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;">Pending Reports</div>
        </div>
      </div>
    </div>

    <!-- Flagged Reports Queue -->
    <div class="card" style="background: var(--bg-surface); padding: 1.25rem; border: 1px solid var(--border-color); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); margin-bottom: 1.5rem;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; padding-bottom: 0.75rem; border-bottom: 1px solid var(--border-color);">
        <h3 style="font-size: 1.15rem; margin: 0; display: flex; align-items: center; gap: 0.45rem;">
          <span>🚩</span> Flagged Content Review Queue
        </h3>
        <span id="admin-queue-count" class="badge badge-secondary">Loading...</span>
      </div>
      <div id="admin-reports-queue">
        <div style="text-align: center; padding: 2.5rem; color: var(--text-muted);">
          <div style="font-size: 2rem; animation: spin 1s infinite linear; display: inline-block;">🔍</div>
          <p style="margin-top: 0.5rem;">Inspecting moderation queue...</p>
        </div>
      </div>
    </div>

    <!-- Registered Users & Member Management Section -->
    <div class="card" style="background: var(--bg-surface); padding: 1.25rem; border: 1px solid var(--border-color); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; padding-bottom: 0.75rem; border-bottom: 1px solid var(--border-color); flex-wrap: wrap; gap: 0.75rem;">
        <div>
          <h3 style="font-size: 1.15rem; margin: 0; display: flex; align-items: center; gap: 0.45rem;">
            <span>👥</span> Community Member & User Moderation
          </h3>
          <p style="font-size: 0.8rem; color: var(--text-muted); margin: 0.2rem 0 0 0;">Inspect accounts, view emails, and remove bad actors</p>
        </div>
        <div style="display: flex; gap: 0.5rem; align-items: center;">
          <input type="text" id="admin-user-search-input" class="form-control" style="font-size: 0.85rem; padding: 0.35rem 0.75rem; width: 220px;" placeholder="Search username, email..." oninput="handleAdminUserSearch(this.value)" />
        </div>
      </div>
      <div id="admin-users-list">
        <div style="text-align: center; padding: 2rem; color: var(--text-muted);">
          Loading registered users...
        </div>
      </div>
    </div>
  `;

  // Fetch stats, reports, and users in parallel
  await Promise.all([
    fetchAdminStats(),
    fetchAdminReports(),
    fetchAdminUsers()
  ]);
}

async function fetchAdminStats() {
  try {
    const data = await apiRequest("/api/admin/stats");
    if (data.stats) {
      const uEl = document.getElementById("stat-admin-users");
      const rEl = document.getElementById("stat-admin-recipes");
      const pEl = document.getElementById("stat-admin-posts");
      const repEl = document.getElementById("stat-admin-reports");
      if (uEl) uEl.textContent = data.stats.total_users;
      if (rEl) rEl.textContent = data.stats.total_recipes;
      if (pEl) pEl.textContent = data.stats.total_posts;
      if (repEl) repEl.textContent = data.stats.total_reports;
    }
  } catch (err) {
    console.error("Error fetching admin stats:", err);
  }
}

async function fetchAdminReports() {
  const queueEl = document.getElementById("admin-reports-queue");
  const countEl = document.getElementById("admin-queue-count");
  if (!queueEl) return;

  try {
    const data = await apiRequest("/api/admin/reports");
    currentAdminReports = data.reports || [];
    if (countEl) countEl.textContent = `${currentAdminReports.length} pending`;

    if (currentAdminReports.length === 0) {
      queueEl.innerHTML = `
        <div style="text-align: center; padding: 3rem 1rem; color: var(--text-muted);">
          <span style="font-size: 3rem; display: block; margin-bottom: 0.75rem;">🎉</span>
          <h4 style="font-size: 1.1rem; color: var(--text-main); margin-bottom: 0.25rem;">Moderation Queue Clean!</h4>
          <p style="font-size: 0.85rem; max-width: 400px; margin: 0 auto;">No community posts or comments have pending moderation flags at this time.</p>
        </div>
      `;
      return;
    }

    queueEl.innerHTML = currentAdminReports.map(report => `
      <div style="background: var(--bg-surface-subtle); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 1.1rem; margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.65rem; flex-wrap: wrap; gap: 0.5rem;">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span class="badge badge-danger">🚩 ${escapeHtml(report.reason)}</span>
            <span style="font-size: 0.82rem; color: var(--text-muted);">Reported by <b>@${escapeHtml(report.reporter_username)}</b></span>
          </div>
          <span style="font-size: 0.75rem; color: var(--text-light);">${new Date(report.created_at).toLocaleString()}</span>
        </div>

        <div style="background: var(--bg-surface); padding: 0.85rem; border-radius: var(--radius-sm); border: 1px solid var(--border-color); margin-bottom: 0.85rem; font-size: 0.88rem; line-height: 1.45;">
          ${report.post_id ? `
            <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem;">Post #${report.post_id}</div>
            <p style="margin: 0; color: var(--text-main);">${escapeHtml(report.post_content || '[Post Content Removed or Unavailable]')}</p>
          ` : ''}
          ${report.comment_id ? `
            <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem;">Comment #${report.comment_id}</div>
            <p style="margin: 0; color: var(--text-main); font-style: italic;">"${escapeHtml(report.comment_content || '[Comment Removed]')}"</p>
          ` : ''}
        </div>

        <div style="display: flex; justify-content: flex-end; gap: 0.5rem; flex-wrap: wrap;">
          <button class="btn btn-secondary btn-sm" onclick="executeReportAction(${report.id}, 'dismiss')">
            ✅ Dismiss Flag
          </button>
          ${report.post_id ? `
            <button class="btn btn-secondary btn-sm" style="color: var(--accent);" onclick="executeReportAction(${report.id}, 'hide_post')">
              🙈 Hide Post
            </button>
            <button class="btn btn-danger btn-sm" onclick="executeReportAction(${report.id}, 'delete_post')">
              🗑️ Delete Post
            </button>
          ` : ''}
          ${report.comment_id ? `
            <button class="btn btn-secondary btn-sm" style="color: var(--accent);" onclick="executeReportAction(${report.id}, 'hide_comment')">
              🙈 Hide Comment
            </button>
          ` : ''}
        </div>
      </div>
    `).join("");
  } catch (err) {
    queueEl.innerHTML = `
      <div style="text-align: center; padding: 2rem; color: var(--danger);">
        Error loading reports: ${escapeHtml(err.message)}
      </div>
    `;
  }
}

function handleAdminUserSearch(query) {
  clearTimeout(adminUserSearchDebounce);
  adminUserSearchDebounce = setTimeout(() => {
    fetchAdminUsers(query);
  }, 250);
}

async function fetchAdminUsers(query = "") {
  const container = document.getElementById("admin-users-list");
  if (!container) return;

  try {
    let url = "/api/admin/users";
    if (query) url += `?q=${encodeURIComponent(query)}`;
    const data = await apiRequest(url);
    const users = data.users || [];

    if (users.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 2rem; color: var(--text-muted);">
          No users found matching "${escapeHtml(query)}"
        </div>
      `;
      return;
    }

    container.innerHTML = `
      <div style="overflow-x: auto;">
        <table style="width: 100%; border-collapse: collapse; font-size: 0.88rem; text-align: left;">
          <thead>
            <tr style="border-bottom: 1px solid var(--border-color); color: var(--text-light); font-size: 0.75rem; text-transform: uppercase;">
              <th style="padding: 0.6rem 0.75rem;">User</th>
              <th style="padding: 0.6rem 0.75rem;">Email</th>
              <th style="padding: 0.6rem 0.75rem;">Role</th>
              <th style="padding: 0.6rem 0.75rem;">Content Stats</th>
              <th style="padding: 0.6rem 0.75rem;">Joined</th>
              <th style="padding: 0.6rem 0.75rem; text-align: right;">Action</th>
            </tr>
          </thead>
          <tbody>
            ${users.map(u => {
              const isSelf = currentUser && currentUser.id === u.id;
              return `
                <tr style="border-bottom: 1px solid var(--border-subtle);">
                  <td style="padding: 0.75rem;">
                    <div style="display: flex; align-items: center; gap: 0.6rem;">
                      <img src="${escapeHtml(u.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" style="width: 32px; height: 32px; border-radius: 50%;" />
                      <div>
                        <div style="font-weight: 700; color: var(--text-main); cursor: pointer;" onclick="openUserProfile('${escapeHtml(u.username)}')">${escapeHtml(u.display_name || u.username)}</div>
                        <div style="font-size: 0.75rem; color: var(--text-light);">@${escapeHtml(u.username)}</div>
                      </div>
                    </div>
                  </td>
                  <td style="padding: 0.75rem; color: var(--text-muted); font-size: 0.82rem;">${escapeHtml(u.email || '-')}</td>
                  <td style="padding: 0.75rem;">
                    ${u.is_admin ? '<span class="badge badge-primary">Admin</span>' : '<span class="badge badge-secondary">Member</span>'}
                  </td>
                  <td style="padding: 0.75rem; color: var(--text-muted); font-size: 0.82rem;">
                    ${u.recipe_count} recipes • ${u.post_count} posts
                  </td>
                  <td style="padding: 0.75rem; color: var(--text-light); font-size: 0.8rem;">
                    ${new Date(u.created_at).toLocaleDateString()}
                  </td>
                  <td style="padding: 0.75rem; text-align: right;">
                    ${!isSelf ? `
                      <button class="btn btn-danger btn-sm" style="padding: 3px 8px; font-size: 0.78rem;" onclick="adminRemoveUserDirect(${u.id}, '${escapeHtml(u.username)}')">
                        🗑️ Remove User
                      </button>
                    ` : '<span style="font-size: 0.78rem; color: var(--text-light);">(You)</span>'}
                  </td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div style="text-align: center; padding: 2rem; color: var(--danger);">Error loading users: ${escapeHtml(err.message)}</div>`;
  }
}

async function adminRemoveUserDirect(userId, username) {
  if (!confirm(`Are you sure you want to PERMANENTLY REMOVE @${username}?\n\nThis will immediately delete their account, profile, recipes, posts, and comments.`)) {
    return;
  }

  try {
    const res = await apiRequest(`/api/admin/users/${userId}`, { method: "DELETE" });
    showToast(res.message || `User @${username} removed`, "success");
    loadAdminDashboardView();
  } catch (err) {
    showToast("Error deleting user: " + err.message, "error");
  }
}

async function executeReportAction(reportId, action) {
  try {
    const res = await apiRequest(`/api/admin/reports/${reportId}/action`, {
      method: "POST",
      body: JSON.stringify({ action })
    });
    showToast(res.message || `Action completed`, "success");
    loadAdminDashboardView();
  } catch (err) {
    showToast("Error processing report: " + err.message, "error");
  }
}

async function purgeOffensiveAccounts() {
  if (!confirm("Are you sure you want to scan and purge all accounts containing profanity, slurs, or evasion handles?")) {
    return;
  }

  try {
    const res = await apiRequest("/api/admin/users/purge-offensive", { method: "POST" });
    showToast(res.message || "Purge complete", "info");
    loadAdminDashboardView();
  } catch (err) {
    showToast("Error during purge: " + err.message, "error");
  }
}

async function purgeStressTestData() {
  if (!confirm("Are you sure you want to permanently purge all virtual stress test accounts, fake recipes, twists, comments, and metrics?")) {
    return;
  }

  try {
    const res = await apiRequest("/api/admin/purge-stress-data", { method: "POST" });
    showToast(res.message || "Stress test data purged successfully!", "success");
    loadAdminDashboardView();
  } catch (err) {
    showToast("Error during purge: " + err.message, "error");
  }
}



