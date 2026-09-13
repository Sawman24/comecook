/* ==============================================================================
   COOKED - In-App Notification Bell & Activity Inbox Module
   ============================================================================== */

let notificationPollTimer = null;
let lastUnreadCount = 0;

/**
 * Initialize notification polling when user is authenticated.
 */
function initNotificationEngine() {
  if (currentUser) {
    checkNotifications();
    if (!notificationPollTimer) {
      notificationPollTimer = setInterval(checkNotifications, 25000); // Check every 25s
    }
  } else {
    stopNotificationPolling();
    updateNotificationBadge(0);
  }
}

/**
 * Stop polling when user logs out.
 */
function stopNotificationPolling() {
  if (notificationPollTimer) {
    clearInterval(notificationPollTimer);
    notificationPollTimer = null;
  }
}

// Page Visibility Engine: pause polling when tab is hidden, immediately refresh on focus
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    if (notificationPollTimer) {
      clearInterval(notificationPollTimer);
      notificationPollTimer = null;
    }
  } else {
    if (currentUser) {
      checkNotifications();
      if (!notificationPollTimer) {
        notificationPollTimer = setInterval(checkNotifications, 25000);
      }
    }
  }
});

/**
 * Fetch latest notifications and update badge.
 */
async function checkNotifications() {
  if (!currentUser) return;
  try {
    const res = await apiRequest("/api/notifications");
    if (res.success) {
      updateNotificationBadge(res.unread_count || 0);
      const dropdown = document.getElementById("notif-dropdown");
      if (dropdown && dropdown.style.display !== "none") {
        renderNotificationsList(res.notifications || []);
      }
    }
  } catch (err) {
    // Silent fail on background poll
  }
}

/**
 * Update the navbar bell notification badge counter.
 */
function updateNotificationBadge(unreadCount) {
  lastUnreadCount = unreadCount;
  const badge = document.getElementById("notif-badge");
  if (!badge) return;

  if (unreadCount > 0) {
    badge.textContent = unreadCount > 99 ? "99+" : unreadCount;
    badge.style.display = "flex";
    badge.classList.add("pulse");
  } else {
    badge.style.display = "none";
    badge.classList.remove("pulse");
  }
}

/**
 * Toggle the notification dropdown menu.
 */
async function toggleNotificationDropdown(e) {
  if (e) e.stopPropagation();
  const dropdown = document.getElementById("notif-dropdown");
  if (!dropdown) return;

  const isHidden = dropdown.style.display === "none" || dropdown.classList.contains("hidden");
  if (isHidden) {
    dropdown.style.display = "block";
    dropdown.classList.remove("hidden");
    
    // Fetch and render immediately
    const container = document.getElementById("notif-list-container");
    if (container) {
      container.innerHTML = `<div style=\"text-align: center; padding: 1.5rem; color: var(--text-light); font-size: 0.85rem;\">Loading activity...</div>`;
    }
    
    try {
      const res = await apiRequest("/api/notifications");
      if (res.success) {
        renderNotificationsList(res.notifications || []);
        updateNotificationBadge(res.unread_count || 0);
      }
    } catch (err) {
      if (container) {
        container.innerHTML = `<div style=\"text-align: center; padding: 1.5rem; color: var(--danger); font-size: 0.85rem;\">Failed to load notifications</div>`;
      }
    }
  } else {
    closeNotificationDropdown();
  }
}

/**
 * Close notification dropdown.
 */
function closeNotificationDropdown() {
  const dropdown = document.getElementById("notif-dropdown");
  if (dropdown) {
    dropdown.style.display = "none";
    dropdown.classList.add("hidden");
  }
}

/**
 * Render the list of notifications inside the dropdown.
 */
function renderNotificationsList(notifications) {
  const container = document.getElementById("notif-list-container");
  if (!container) return;

  if (!notifications || notifications.length === 0) {
    container.innerHTML = `
      <div class="notif-empty-state">
        <span style="font-size: 2rem; display: block; margin-bottom: 0.35rem;">🔔</span>
        <p style="font-weight: 600; font-size: 0.9rem; margin-bottom: 0.2rem;">All caught up!</p>
        <p style="font-size: 0.8rem; color: var(--text-muted);">No new activity or kitchen notifications.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = notifications.map(notif => {
    const isUnread = notif.is_read === 0;
    const actorAvatar = notif.actor_avatar || "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100";
    const actorName = notif.actor_display_name || notif.actor_username || "A chef";
    
    let icon = "🔔";
    let iconBg = "var(--primary-light)";
    if (notif.type === "like") {
      icon = "❤️";
      iconBg = "var(--danger-light)";
    } else if (notif.type === "comment") {
      icon = "💬";
      iconBg = "var(--secondary-light)";
    } else if (notif.type === "review") {
      icon = "⭐";
      iconBg = "rgba(245, 158, 11, 0.18)";
    } else if (notif.type === "fork") {
      icon = "🍴";
      iconBg = "var(--primary-light)";
    } else if (notif.type === "follow") {
      icon = "👨‍🍳";
      iconBg = "rgba(2, 132, 199, 0.18)";
    }

    const timeAgo = formatTimeAgo(notif.created_at);

    return `
      <div class="notif-item ${isUnread ? "unread" : ""}" onclick="handleNotificationItemClick(${notif.id}, \"${escapeHtml(notif.entity_type || "")}\", ${notif.entity_id || 0}, \"${escapeHtml(notif.actor_username || "")}\")">
        <div class="notif-avatar-wrap">
          <img src="${escapeHtml(actorAvatar)}" class="avatar-sm" alt="${escapeHtml(actorName)}" />
          <span class="notif-type-icon" style="background: ${iconBg};">${icon}</span>
        </div>
        <div class="notif-content">
          <p class="notif-message">${escapeHtml(notif.message)}</p>
          <span class="notif-time">${timeAgo}</span>
        </div>
        ${isUnread ? "<span class="notif-unread-dot" title="Unread"></span>" : ""}
      </div>
    `;
  }).join("");
}

/**
 * Handle clicking a notification: marks as read and navigates to target.
 */
async function handleNotificationItemClick(notifId, entityType, entityId, actorUsername) {
  closeNotificationDropdown();

  // Mark as read in background
  try {
    await apiRequest("/api/notifications/read", {
      method: "POST",
      body: JSON.stringify({ notification_ids: [notifId] })
    });
    checkNotifications();
  } catch (err) {
    // Ignore error
  }

  // Deep-link to entity
  if (entityType === "recipe" && entityId) {
    viewRecipeDetail(entityId);
  } else if (entityType === "post" && entityId) {
    navigateTo("feed");
    setTimeout(() => {
      openCommentsModal(entityId);
    }, 250);
  } else if (entityType === "user" && actorUsername) {
    openUserProfile(actorUsername);
  }
}

/**
 * Mark all notifications as read.
 */
async function markAllNotificationsRead() {
  try {
    await apiRequest("/api/notifications/read", {
      method: "POST",
      body: JSON.stringify({})
    });
    showToast("All notifications marked as read", "success");
    checkNotifications();
  } catch (err) {
    showToast("Failed to mark notifications as read", "error");
  }
}

// Global click listener to close dropdown on clicking outside
document.addEventListener("click", (e) => {
  const notifWrapper = document.getElementById("notif-wrapper");
  const dropdown = document.getElementById("notif-dropdown");
  if (notifWrapper && dropdown && !notifWrapper.contains(e.target)) {
    closeNotificationDropdown();
  }
});
