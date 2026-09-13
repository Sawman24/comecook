/* ==============================================================================
   COOKED - Direct Messaging & Kitchen Whispers Client Module (With Message Requests)
   ============================================================================== */

let currentDmPartnerId = null;
let currentDmPartnerUsername = null;
let dmPollingInterval = null;
let currentDmTab = "primary"; // 'primary' | 'requests'
let allDmConversationsData = { primary: [], requests: [] };
let shareModalPayload = { recipe_id: null, post_id: null, defaultText: "" };

/**
 * Initialize DM engine & unread badge counter
 */
function initDirectMessaging() {
  const dmNavWrapper = document.getElementById("dm-nav-wrapper");
  if (dmNavWrapper) {
    dmNavWrapper.style.display = currentUser ? "flex" : "none";
  }

  if (currentUser) {
    updateUnreadDmCount();
    if (!dmPollingInterval) {
      dmPollingInterval = setInterval(updateUnreadDmCount, 15000);
    }
  } else {
    if (dmPollingInterval) {
      clearInterval(dmPollingInterval);
      dmPollingInterval = null;
    }
  }
}

// Page Visibility Engine: pause DM polling when tab is hidden, immediately refresh on focus
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    if (dmPollingInterval) {
      clearInterval(dmPollingInterval);
      dmPollingInterval = null;
    }
  } else {
    if (currentUser) {
      updateUnreadDmCount();
      if (!dmPollingInterval) {
        dmPollingInterval = setInterval(updateUnreadDmCount, 15000);
      }
    }
  }
});

async function updateUnreadDmCount() {
  if (!currentUser) return;
  try {
    const data = await apiRequest("/api/messages/unread-count");
    const badge = document.getElementById("dm-badge");
    const reqBadge = document.getElementById("dm-requests-count-badge");

    const count = (data.unread_count || 0) + (data.unread_requests_count || 0);
    if (badge) {
      if (count > 0) {
        badge.textContent = count > 99 ? "99+" : count;
        badge.style.display = "flex";
      } else {
        badge.style.display = "none";
      }
    }

    if (reqBadge) {
      const rCount = data.unread_requests_count || 0;
      if (rCount > 0) {
        reqBadge.textContent = rCount > 99 ? "99+" : rCount;
        reqBadge.style.display = "inline-block";
      } else {
        reqBadge.style.display = "none";
      }
    }
  } catch (e) {
    // Silent fail for polling
  }
}

/**
 * Toggle the Direct Messages Drawer
 */
async function toggleMessagesDrawer(event) {
  if (event) event.stopPropagation();
  if (!currentUser) {
    openAuthModal("login");
    return;
  }

  const drawer = document.getElementById("dm-drawer-modal");
  if (!drawer) return;

  if (drawer.classList.contains("show")) {
    closeMessagesDrawer();
  } else {
    drawer.classList.add("show");
    await loadDmConversations();
  }
}

function closeMessagesDrawer() {
  const drawer = document.getElementById("dm-drawer-modal");
  if (drawer) drawer.classList.remove("show");
  currentDmPartnerId = null;
  currentDmPartnerUsername = null;
  updateUnreadDmCount();
}

/**
 * Switch DM Tab between Primary and Requests
 */
function switchDmTab(tab) {
  currentDmTab = tab;
  const primBtn = document.getElementById("dm-tab-btn-primary");
  const reqBtn = document.getElementById("dm-tab-btn-requests");

  if (primBtn && reqBtn) {
    primBtn.classList.toggle("active", tab === "primary");
    reqBtn.classList.toggle("active", tab === "requests");
  }

  renderConversationList();
}

/**
 * Load all conversation threads for current user
 */
async function loadDmConversations() {
  const listEl = document.getElementById("dm-conversations-list");
  if (!listEl) return;

  listEl.innerHTML = `<div style="text-align: center; padding: 2rem; color: var(--text-light); font-size: 0.85rem;">Loading conversations...</div>`;

  try {
    const data = await apiRequest("/api/messages/conversations");
    allDmConversationsData = {
      primary: data.primary || [],
      requests: data.requests || []
    };

    const reqBadge = document.getElementById("dm-requests-count-badge");
    if (reqBadge) {
      const count = data.requests_count || allDmConversationsData.requests.length;
      if (count > 0) {
        reqBadge.textContent = count > 99 ? "99+" : count;
        reqBadge.style.display = "inline-block";
      } else {
        reqBadge.style.display = "none";
      }
    }

    renderConversationList();

    const activeList = currentDmTab === "primary" ? allDmConversationsData.primary : allDmConversationsData.requests;
    if (!currentDmPartnerId && activeList.length > 0) {
      openDmThread(activeList[0].partner.id, activeList[0].partner.username);
    }
  } catch (err) {
    listEl.innerHTML = `<div style="color: var(--danger); padding: 1rem; text-align: center;">Error loading chats: ${escapeHtml(err.message)}</div>`;
  }
}

/**
 * Render conversation list based on active tab and search query
 */
function renderConversationList(searchQuery = "") {
  const listEl = document.getElementById("dm-conversations-list");
  if (!listEl) return;

  let list = currentDmTab === "primary" ? (allDmConversationsData.primary || []) : (allDmConversationsData.requests || []);

  if (searchQuery.trim()) {
    const q = searchQuery.toLowerCase();
    list = list.filter(c =>
      (c.partner.username && c.partner.username.toLowerCase().includes(q)) ||
      (c.partner.display_name && c.partner.display_name.toLowerCase().includes(q)) ||
      (c.last_message && c.last_message.message && c.last_message.message.toLowerCase().includes(q))
    );
  }

  if (list.length === 0) {
    if (currentDmTab === "requests") {
      listEl.innerHTML = `
        <div style="text-align: center; padding: 2.5rem 1rem; color: var(--text-muted);">
          <span style="font-size: 2rem; display: block; margin-bottom: 0.5rem;">📬</span>
          <p style="font-weight: 600; font-size: 0.95rem;">No message requests</p>
          <p style="font-size: 0.8rem; margin-top: 0.25rem;">Requests from non-friends will appear here for review.</p>
        </div>
      `;
    } else {
      listEl.innerHTML = `
        <div style="text-align: center; padding: 2.5rem 1rem; color: var(--text-muted);">
          <span style="font-size: 2rem; display: block; margin-bottom: 0.5rem;">💬</span>
          <p style="font-weight: 600; font-size: 0.95rem;">No whispers yet</p>
          <p style="font-size: 0.8rem; margin-top: 0.25rem;">Whisper with mutual friends or send a request to any chef!</p>
        </div>
      `;
    }

    if (!currentDmPartnerId) {
      const activeEl = document.getElementById("dm-active-thread-container");
      if (activeEl) {
        activeEl.innerHTML = `
          <div class="dm-empty-thread-placeholder">
            <span style="font-size: 3rem;">👨‍🍳</span>
            <h3>Kitchen Whispers</h3>
            <p>Select a chef from the left to start cooking together privately.</p>
          </div>
        `;
      }
    }
    return;
  }

  listEl.innerHTML = list.map(c => {
    const p = c.partner;
    const isSelected = currentDmPartnerId && currentDmPartnerId === p.id;
    const lastSnippet = c.last_message ? (c.last_message.message || (c.last_message.recipe_id ? 'Shared a recipe' : 'Shared a post')) : 'No messages yet';
    const timeStr = c.last_message ? formatRelativeTime(c.last_message.created_at) : '';
    const isPendingOutgoing = c.request_info && c.request_info.status === 'pending' && c.request_info.is_sender;

    return `
      <div class="dm-convo-item ${isSelected ? 'active' : ''} ${c.unread_count > 0 ? 'unread' : ''}" onclick="openDmThread(${p.id}, '${escapeHtml(p.username)}')">
        <img src="${escapeHtml(p.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" />
        <div style="flex: 1; min-width: 0;">
          <div style="display: flex; justify-content: space-between; align-items: baseline; gap: 0.25rem;">
            <span class="dm-convo-name">${escapeHtml(p.display_name || p.username)} ${p.is_verified ? '⭐' : ''}</span>
            <span class="dm-convo-time">${timeStr}</span>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.15rem; gap: 0.25rem;">
            <span class="dm-convo-snippet">${escapeHtml(lastSnippet)}</span>
            ${isPendingOutgoing ? `<span class="badge badge-secondary" style="font-size: 0.6rem; flex-shrink: 0;">Pending</span>` : ''}
            ${c.unread_count > 0 ? `<span class="dm-unread-pill">${c.unread_count}</span>` : ''}
          </div>
        </div>
      </div>
    `;
  }).join("");
}

function filterDmConversations(query) {
  renderConversationList(query);
}

/**
 * Open a specific DM thread with a partner
 */
async function openDmThread(partnerId, partnerUsername) {
  currentDmPartnerId = partnerId;
  currentDmPartnerUsername = partnerUsername;

  document.querySelectorAll(".dm-convo-item").forEach(el => el.classList.remove("active"));
  updateUnreadDmCount();

  const container = document.getElementById("dm-active-thread-container");
  if (!container) return;

  container.innerHTML = `<div style="text-align: center; padding: 3rem; color: var(--text-light);">Loading whisper thread...</div>`;

  try {
    const data = await apiRequest(`/api/messages/${partnerId}`);
    const partner = data.partner;
    const messages = data.messages || [];
    const isBlocked = data.is_blocked;
    const isFriend = data.is_friend;
    const isPendingRequest = data.is_pending_request;
    const isRequestRecipient = data.is_request_recipient;
    const isRequestSender = data.is_request_sender;

    container.innerHTML = `
      <!-- Chat Header -->
      <div class="dm-thread-header">
        <div style="display: flex; align-items: center; gap: 0.65rem; cursor: pointer;" onclick="openUserProfile('${escapeHtml(partner.username)}')">
          <img src="${escapeHtml(partner.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" />
          <div>
            <div style="display: flex; align-items: center; gap: 0.4rem;">
              <h4 style="font-size: 0.95rem; margin: 0; line-height: 1.2;">${escapeHtml(partner.display_name || partner.username)} ${partner.is_verified ? '⭐' : ''}</h4>
              ${isFriend ? `<span class="dm-friend-pill">👥 Friend</span>` : (isPendingRequest ? `<span class="badge badge-secondary" style="font-size: 0.62rem;">✉️ Request</span>` : '')}
            </div>
            <span style="font-size: 0.75rem; color: var(--text-light);">@${escapeHtml(partner.username)}</span>
          </div>
        </div>
        <div style="display: flex; gap: 0.5rem;">
          ${isFriend ? `<button class="btn btn-secondary btn-sm" onclick="openShareInDmModal(null, null, ${partner.id})" title="Attach Recipe">🍲 Attach Recipe</button>` : ''}
        </div>
      </div>

      <!-- Chat Messages Scroll Area -->
      <div class="dm-messages-stream" id="dm-messages-stream">
        ${messages.length === 0 ? `
          <div style="text-align: center; padding: 3rem 1rem; color: var(--text-muted);">
            <p>No messages in this whisper thread yet.</p>
            <p style="font-size: 0.8rem; margin-top: 0.25rem;">
              ${isFriend ? `Say hello to Chef ${escapeHtml(partner.display_name)} or exchange cooking secrets!` : `Send a message request to start whispering with Chef ${escapeHtml(partner.display_name)}.`}
            </p>
          </div>
        ` : messages.map(m => renderDmBubble(m)).join("")}
      </div>

      <!-- Request Action Banner or Input Area -->
      ${isBlocked ? `
        <div style="padding: 1rem; background: var(--bg-surface); text-align: center; font-size: 0.85rem; color: var(--danger); border-top: 1px solid var(--border-color);">
          🚫 Messaging is disabled because one of you has blocked the other.
        </div>
      ` : (isPendingRequest && isRequestRecipient ? `
        <div class="dm-request-banner">
          <div class="dm-request-banner-info">
            <span>✉️</span>
            <div>
              <strong>Chef @${escapeHtml(partner.username)}</strong> sent you a message request.
              <div style="font-size: 0.75rem; color: var(--text-muted);">Accept to start whispering and move this thread to Primary.</div>
            </div>
          </div>
          <div class="dm-request-actions">
            <button class="btn btn-outline btn-sm btn-danger" onclick="toggleBlockChef(${partner.id}, '${escapeHtml(partner.username)}', true)">🚫 Block</button>
            <button class="btn btn-secondary btn-sm" onclick="declineMessageRequest(${partner.id})">✕ Decline</button>
            <button class="btn btn-primary btn-sm" onclick="acceptMessageRequest(${partner.id})">✓ Accept Request</button>
          </div>
        </div>
      ` : (isPendingRequest && isRequestSender ? `
        <div class="dm-pending-notice">
          <span>⏳</span>
          <span>Message request sent. Waiting for Chef @${escapeHtml(partner.username)} to accept before you can send more messages.</span>
        </div>
      ` : `
        <form class="dm-input-area" onsubmit="handleSendDmSubmit(event, ${partner.id})">
          <input type="text" id="dm-message-input" class="form-control" placeholder="${isFriend ? 'Whisper a culinary tip or message...' : 'Send a message request to Chef...'}" autocomplete="off" required />
          <button type="submit" class="btn btn-primary btn-sm">${isFriend ? 'Send' : 'Send Request'}</button>
        </form>
      `))}
    `;

    const streamEl = document.getElementById("dm-messages-stream");
    if (streamEl) {
      streamEl.scrollTop = streamEl.scrollHeight;
    }
  } catch (err) {
    container.innerHTML = `<div style="color: var(--danger); padding: 2rem; text-align: center;">Error loading messages: ${escapeHtml(err.message)}</div>`;
  }
}

function renderDmBubble(m) {
  const isMine = currentUser && m.sender_id === currentUser.id;
  return `
    <div class="dm-bubble-row ${isMine ? 'mine' : 'theirs'}">
      <div class="dm-bubble ${isMine ? 'mine' : 'theirs'}">
        ${m.recipe_id && m.recipe_title ? `
          <div class="dm-attached-card" onclick="viewRecipeDetail(${m.recipe_id})">
            ${m.recipe_image ? `<img src="${escapeHtml(m.recipe_image)}" />` : ''}
            <div>
              <span class="badge badge-primary" style="font-size: 0.65rem;">Shared Recipe</span>
              <h5 style="margin: 0.15rem 0; font-size: 0.85rem;">${escapeHtml(m.recipe_title)}</h5>
              <span style="font-size: 0.72rem; color: var(--text-light);">${escapeHtml(m.recipe_difficulty || 'Medium')}</span>
            </div>
          </div>
        ` : ''}

        ${m.post_id && m.post_snippet ? `
          <div class="dm-attached-card">
            ${m.post_image ? `<img src="${escapeHtml(m.post_image)}" />` : ''}
            <div>
              <span class="badge badge-secondary" style="font-size: 0.65rem;">Shared Post</span>
              <p style="margin: 0.15rem 0; font-size: 0.8rem;">"${escapeHtml(m.post_snippet)}"</p>
            </div>
          </div>
        ` : ''}

        ${m.message ? `<div class="dm-bubble-text">${escapeHtml(m.message)}</div>` : ''}
        <span class="dm-bubble-time">${formatRelativeTime(m.created_at)}</span>
      </div>
    </div>
  `;
}

async function handleSendDmSubmit(e, partnerId) {
  e.preventDefault();
  const input = document.getElementById("dm-message-input");
  if (!input) return;
  const message = input.value.trim();
  if (!message) return;

  try {
    input.disabled = true;
    const res = await apiRequest(`/api/messages/${partnerId}`, {
      method: "POST",
      body: JSON.stringify({ message })
    });
    input.value = "";
    input.disabled = false;

    if (res.is_request) {
      showToast("Message request sent!", "success");
      await loadDmConversations();
      await openDmThread(partnerId, currentDmPartnerUsername);
    } else {
      const streamEl = document.getElementById("dm-messages-stream");
      if (streamEl && res.dm) {
        const bubbleWrap = document.createElement("div");
        bubbleWrap.innerHTML = renderDmBubble(res.dm);
        streamEl.appendChild(bubbleWrap.firstElementChild);
        streamEl.scrollTop = streamEl.scrollHeight;
      }
      input.focus();
    }
  } catch (err) {
    if (input) input.disabled = false;
    showToast("Failed to send message: " + err.message, "error");
  }
}

/**
 * Accept incoming message request
 */
async function acceptMessageRequest(partnerId) {
  try {
    const res = await apiRequest(`/api/messages/requests/${partnerId}/accept`, { method: "POST" });
    showToast(res.message || "Message request accepted!", "success");
    await loadDmConversations();
    await openDmThread(partnerId, currentDmPartnerUsername);
  } catch (err) {
    showToast("Error accepting request: " + err.message, "error");
  }
}

/**
 * Decline incoming message request
 */
async function declineMessageRequest(partnerId) {
  try {
    const res = await apiRequest(`/api/messages/requests/${partnerId}/decline`, { method: "POST" });
    showToast(res.message || "Message request declined.", "info");
    currentDmPartnerId = null;
    currentDmPartnerUsername = null;
    await loadDmConversations();
    const activeEl = document.getElementById("dm-active-thread-container");
    if (activeEl) {
      activeEl.innerHTML = `
        <div class="dm-empty-thread-placeholder">
          <span style="font-size: 3rem;">👨‍🍳</span>
          <h3>Kitchen Whispers</h3>
          <p>Request declined. Select another conversation.</p>
        </div>
      `;
    }
  } catch (err) {
    showToast("Error declining request: " + err.message, "error");
  }
}

/**
 * Open Direct Message directly with a user (e.g. from their profile card)
 */
async function launchDirectMessageWithUser(userId, username) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }
  const drawer = document.getElementById("dm-drawer-modal");
  if (drawer) {
    drawer.classList.add("show");
  }
  await loadDmConversations();
  await openDmThread(userId, username);
}

/**
 * "Share in DM" modal (for recipes & posts)
 */
async function openShareInDmModal(recipeId = null, postId = null, preselectedUserId = null) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }

  shareModalPayload = { recipe_id: recipeId, post_id: postId, defaultText: "" };
  const modal = document.getElementById("share-dm-modal");
  if (!modal) return;

  const select = document.getElementById("share-dm-recipient-select");
  if (select) {
    try {
      const data = await apiRequest("/api/users");
      const users = (data.users || []).filter(u => u.id !== currentUser.id);
      select.innerHTML = users.map(u => `
        <option value="${u.id}" ${preselectedUserId && preselectedUserId == u.id ? 'selected' : ''}>
          @${escapeHtml(u.username)} (${escapeHtml(u.display_name)})
        </option>
      `).join("");
    } catch (e) {
      select.innerHTML = `<option value="">Failed to load chefs</option>`;
    }
  }

  modal.classList.add("show");
}

function closeShareInDmModal() {
  const modal = document.getElementById("share-dm-modal");
  if (modal) modal.classList.remove("show");
}

async function handleShareInDmSubmit(e) {
  e.preventDefault();
  const select = document.getElementById("share-dm-recipient-select");
  const noteInput = document.getElementById("share-dm-note-input");
  const recipientId = select ? parseInt(select.value) : null;
  const message = noteInput ? noteInput.value.trim() : "";

  if (!recipientId) {
    showToast("Please select a recipient chef", "error");
    return;
  }

  try {
    const res = await apiRequest(`/api/messages/${recipientId}`, {
      method: "POST",
      body: JSON.stringify({
        message: message || "Hey Chef, check this out!",
        recipe_id: shareModalPayload.recipe_id,
        post_id: shareModalPayload.post_id
      })
    });
    showToast(res.message || "Shared via Kitchen Whisper!", "success");
    closeShareInDmModal();
    if (noteInput) noteInput.value = "";
    updateUnreadDmCount();
  } catch (err) {
    showToast("Error sharing: " + err.message, "error");
  }
}
