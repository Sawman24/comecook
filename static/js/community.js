/* ==============================================================================
   COOKED - Social Community Feed, Multi-Reactions, Polls, Mentions & Comments
   ============================================================================== */

let currentFeedFilter = "all";
let currentDietaryFilter = "";
let openCommentsPostId = null;
let postUploadedImageUrl = "";
let isPollEnabledInModal = false;

const REACTION_CONFIG = {
  heart: { emoji: "❤️", name: "Love" },
  chef_kiss: { emoji: "👨‍🍳", name: "Chef's Kiss" },
  fire: { emoji: "🔥", name: "Fire" },
  drool: { emoji: "🤤", name: "Delicious" },
  genius: { emoji: "💡", name: "Genius Tip" }
};

async function loadCommunityFeedView(filter = "all", dietary = "") {
  currentFeedFilter = filter;
  currentDietaryFilter = dietary;
  const container = document.getElementById("main-content-view");
  if (!container) return;

  container.innerHTML = `
    <!-- Feed Filter Bar -->
    <div class="feed-filter-bar">
      <button class="filter-chip ${filter === 'all' && !dietary ? 'active' : ''}" onclick="loadCommunityFeedView('all', '')">🔥 All Feed</button>
      <button class="filter-chip ${filter === 'for_you' ? 'active' : ''}" onclick="loadCommunityFeedView('for_you', '')">✨ For You</button>
      <button class="filter-chip ${filter === 'following' ? 'active' : ''}" onclick="loadCommunityFeedView('following', '')">👥 Following</button>
      <button class="filter-chip ${filter === 'trending' ? 'active' : ''}" onclick="loadCommunityFeedView('trending', '')">📈 Trending</button>
      <button class="filter-chip ${filter === 'question' ? 'active' : ''}" onclick="loadCommunityFeedView('question', '')">❓ Kitchen Questions</button>
      <button class="filter-chip ${filter === 'showcase' ? 'active' : ''}" onclick="loadCommunityFeedView('showcase', '')">📸 Showcases</button>
    </div>

    <!-- Dietary & Allergy Filter Bar -->
    <div class="dietary-filter-bar">
      <span class="dietary-label">Dietary:</span>
      <button class="dietary-chip ${dietary === '' ? 'active' : ''}" onclick="loadCommunityFeedView('${filter}', '')">All Diets</button>
      <button class="dietary-chip ${dietary === 'vegetarian' ? 'active' : ''}" onclick="loadCommunityFeedView('${filter}', 'vegetarian')">🌱 Vegetarian</button>
      <button class="dietary-chip ${dietary === 'vegan' ? 'active' : ''}" onclick="loadCommunityFeedView('${filter}', 'vegan')">🌿 Vegan</button>
      <button class="dietary-chip ${dietary === 'gluten-free' ? 'active' : ''}" onclick="loadCommunityFeedView('${filter}', 'gluten-free')">🌾 Gluten-Free</button>
      <button class="dietary-chip ${dietary === 'keto' ? 'active' : ''}" onclick="loadCommunityFeedView('${filter}', 'keto')">🥑 Keto</button>
      <button class="dietary-chip ${dietary === 'quick' ? 'active' : ''}" onclick="loadCommunityFeedView('${filter}', 'quick')">⚡ Quick (&lt;30m)</button>
    </div>

    <!-- Create Post Card -->
    <div class="create-post-card">
      <div class="create-post-header">
        <img src="${escapeHtml(currentUser?.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" />
        <input type="text" class="form-control" style="border-radius: var(--radius-full); cursor: pointer;" placeholder="Share a culinary tip, ask a cooking question, or start a poll..." onclick="openCreateModal()" readonly />
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 0.5rem; border-top: 1px solid var(--border-subtle);">
        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
          <button class="btn btn-secondary btn-sm" onclick="openCreateModal('showcase')">📸 Photo</button>
          <button class="btn btn-secondary btn-sm" onclick="openCreateModal('question')">❓ Ask Question</button>
          <button class="btn btn-secondary btn-sm" onclick="openCreateModal('post', null, true)">📊 Add Poll</button>
          <button class="btn btn-secondary btn-sm" onclick="openCreateModal('post')">🍲 Attach Recipe</button>
        </div>
        <button class="btn btn-primary btn-sm" onclick="openCreateModal()">Post</button>
      </div>
    </div>

    <!-- Posts Container -->
    <div id="posts-stream-container">
      <div style="text-align: center; padding: 2rem; color: var(--text-light);">Loading community feed...</div>
    </div>
  `;

  await fetchAndRenderPosts();
}

async function fetchAndRenderPosts(searchQuery = "") {
  let url = `/api/posts?type=${encodeURIComponent(currentFeedFilter)}`;
  if (currentDietaryFilter) url += `&dietary=${encodeURIComponent(currentDietaryFilter)}`;
  if (searchQuery) url += `&q=${encodeURIComponent(searchQuery)}`;

  try {
    const data = await apiRequest(url);
    const container = document.getElementById("posts-stream-container");
    if (!container) return;

    if (!data.posts || data.posts.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 3rem 1rem; background: var(--bg-surface); border: 1px dashed var(--border-color); border-radius: var(--radius-lg);">
          <span style="font-size: 2.5rem; display: block; margin-bottom: 0.5rem;">🍳</span>
          <h3>No posts found in this feed</h3>
          <p style="color: var(--text-muted); font-size: 0.9rem; margin-top: 0.25rem;">
            ${currentFeedFilter === 'following' ? 'You are not following anyone yet, or your followed chefs have not posted.' : 'Be the first cook to start the conversation!'}
          </p>
        </div>
      `;
      return;
    }

    container.innerHTML = data.posts.map(post => renderPostCard(post)).join("");
  } catch (err) {
    showToast("Error loading posts: " + err.message, "error");
  }
}

function renderPostCard(post) {
  const isOwner = currentUser && (currentUser.id === post.user_id || currentUser.is_admin === 1);
  const typeBadge = post.post_type === "question" 
    ? `<span class="badge badge-warning">❓ Question</span>` 
    : (post.post_type === "showcase" ? `<span class="badge badge-success">📸 Showcase</span>` : "");
  const stationBadge = post.station_slug
    ? `<span class="badge badge-station" onclick="event.stopPropagation(); navigateToStation('${escapeHtml(post.station_slug)}')">${escapeHtml(post.station_icon || '🍳')} station/${escapeHtml(post.station_slug)}</span>`
    : "";

  // Render author badges
  const authorBadgesHtml = renderBadgesHtml(post.author_badges || []);

  // Reactions summary
  const reactions = post.reactions || { counts: {}, total: 0, user_reaction: null };
  const userRx = reactions.user_reaction;
  const currentEmoji = userRx && REACTION_CONFIG[userRx] ? REACTION_CONFIG[userRx].emoji : "❤️";

  return `
    <div class="post-card" id="post-card-${post.id}">
      <div class="post-header">
        <div class="post-author-info">
          <img src="${escapeHtml(post.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" onclick="openUserProfile('${escapeHtml(post.username)}')" />
          <div>
            <div style="display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
              <span class="author-name" onclick="openUserProfile('${escapeHtml(post.username)}')">${escapeHtml(post.display_name || post.username)}</span>
              ${post.is_verified ? '<span title="Verified Chef">⭐</span>' : ''}
              ${authorBadgesHtml}
              ${typeBadge}
              ${stationBadge}
            </div>
            <span class="author-username">@${escapeHtml(post.username)} • ${formatRelativeTime(post.created_at)}</span>
          </div>
        </div>
        <div style="display: flex; gap: 0.35rem;">
          <button class="btn-icon" title="Share via Whisper (DM)" onclick="openShareInDmModal(null, ${post.id})">💬</button>
          <button class="btn-icon" title="Report" onclick="openReportModal(${post.id}, null)">🚩</button>
          ${isOwner ? `<button class="btn-icon" style="color: var(--danger);" title="Delete" onclick="deletePost(${post.id})">🗑️</button>` : ''}
        </div>
      </div>

      <div class="post-content">${formatPostContent(post.content)}</div>

      ${post.image_url ? `
        <div class="post-image-wrap" onclick="openLightbox('${escapeHtml(post.image_url)}', 'Post by @${escapeHtml(post.username)}')">
          <img src="${escapeHtml(post.image_url)}" alt="Dish photo" />
        </div>
      ` : ''}

      ${post.recipe_id && post.recipe_title ? `
        <div class="post-attached-recipe" onclick="viewRecipeDetail(${post.recipe_id})">
          ${post.recipe_image ? `<img src="${escapeHtml(post.recipe_image)}" />` : ''}
          <div>
            <span class="badge badge-primary" style="font-size: 0.7rem; margin-bottom: 0.2rem;">Attached Recipe</span>
            <h4 style="font-size: 0.95rem;">${escapeHtml(post.recipe_title)}</h4>
            <span style="font-size: 0.78rem; color: var(--text-light);">⏱️ ${post.recipe_total_time || 30} mins • ${escapeHtml(post.recipe_difficulty || 'Medium')}</span>
          </div>
        </div>
      ` : ''}

      ${post.poll ? renderPollCard(post.poll) : ''}

      <!-- Post Actions & Multi-Reaction Picker -->
      <div class="post-actions">
        <div class="action-group">
          <!-- Multi-Reaction Button with Popover -->
          <div class="reaction-wrapper" id="rx-wrapper-${post.id}">
            <button class="post-action-btn rx-main-btn ${userRx ? 'reacted' : ''}" onclick="toggleReactionPicker(${post.id})">
              <span class="rx-btn-icon">${currentEmoji}</span>
              <span class="rx-btn-label">${userRx ? REACTION_CONFIG[userRx].name : 'React'}</span>
            </button>
            <div class="reaction-popover" id="rx-popover-${post.id}">
              <span class="rx-option ${userRx === 'heart' ? 'active' : ''}" title="Love ❤️" onclick="submitPostReaction(${post.id}, 'heart')">❤️</span>
              <span class="rx-option ${userRx === 'chef_kiss' ? 'active' : ''}" title="Chef's Kiss 👨‍🍳" onclick="submitPostReaction(${post.id}, 'chef_kiss')">👨‍🍳</span>
              <span class="rx-option ${userRx === 'fire' ? 'active' : ''}" title="Fire 🔥" onclick="submitPostReaction(${post.id}, 'fire')">🔥</span>
              <span class="rx-option ${userRx === 'drool' ? 'active' : ''}" title="Delicious 🤤" onclick="submitPostReaction(${post.id}, 'drool')">🤤</span>
              <span class="rx-option ${userRx === 'genius' ? 'active' : ''}" title="Genius Tip 💡" onclick="submitPostReaction(${post.id}, 'genius')">💡</span>
            </div>
          </div>

          <!-- Comments Drawer Button -->
          <button class="post-action-btn" onclick="toggleCommentsDrawer(${post.id})">
            <svg style="width: 18px; height: 18px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
            </svg>
            <span>${post.comment_count || 0} Comments</span>
          </button>
        </div>

        <!-- Reaction Pills Count Summary -->
        <div class="reaction-pills-row" id="rx-pills-${post.id}">
          ${renderReactionPillsHtml(post.id, reactions)}
        </div>
      </div>

      <!-- Comments Drawer Container -->
      <div id="comments-container-${post.id}" style="display: none;" class="comments-section"></div>
    </div>
  `;
}

function renderReactionPillsHtml(postId, reactions) {
  if (!reactions || !reactions.counts) return "";
  const pills = [];
  for (const [key, count] of Object.entries(reactions.counts)) {
    if (count > 0) {
      const cfg = REACTION_CONFIG[key] || { emoji: "✨", name: key };
      const isMyChoice = reactions.user_reaction === key;
      pills.push(`
        <button class="reaction-pill ${isMyChoice ? 'active' : ''}" onclick="submitPostReaction(${postId}, '${key}')" title="${cfg.name}">
          <span>${cfg.emoji}</span> <span>${count}</span>
        </button>
      `);
    }
  }
  return pills.join("");
}

function renderPollCard(poll) {
  if (!poll) return "";
  const hasVoted = poll.user_voted_index !== null;

  return `
    <div class="poll-card" id="poll-card-${poll.id}">
      <div class="poll-question">📊 ${escapeHtml(poll.question)}</div>
      <div class="poll-options-list">
        ${poll.options.map(opt => {
          const isSelected = poll.user_voted_index === opt.index;
          return `
            <div class="poll-option-row ${isSelected ? 'selected' : ''}" onclick="castPollVote(${poll.id}, ${opt.index})">
              <div class="poll-progress-bar" style="width: ${hasVoted ? opt.percent : 0}%;"></div>
              <div class="poll-option-content">
                <span class="poll-option-text">${isSelected ? '✓ ' : ''}${escapeHtml(opt.text)}</span>
                ${hasVoted ? `<span class="poll-option-pct">${opt.percent}% (${opt.votes})</span>` : ''}
              </div>
            </div>
          `;
        }).join("")}
      </div>
      <div class="poll-footer">
        <span>${poll.total_votes} total vote${poll.total_votes === 1 ? '' : 's'}</span>
        ${hasVoted ? '<span class="poll-voted-tag">Voted</span>' : '<span style="font-size: 0.78rem; color: var(--text-light);">Click an option to vote</span>'}
      </div>
    </div>
  `;
}

function renderBadgesHtml(badges) {
  if (!badges || badges.length === 0) return "";
  // Show top 2 badges to keep header neat
  return badges.slice(0, 2).map(b => `
    <span class="chef-badge-pill ${b.tier || 'silver'}" title="${escapeHtml(b.name)}: ${escapeHtml(b.description)}">
      ${escapeHtml(b.icon)} ${escapeHtml(b.name)}
    </span>
  `).join("");
}

function formatPostContent(text) {
  if (!text) return "";
  let escaped = escapeHtml(text);
  // Highlight @mentions
  escaped = escaped.replace(/@([a-zA-Z0-9_]{3,30})/g, (match, username) => {
    return `<span class="mention-tag" onclick="event.stopPropagation(); openUserProfile('${username}')">@${username}</span>`;
  });
  // Highlight #tags
  escaped = escaped.replace(/#([a-zA-Z0-9_]{2,30})/g, (match, tag) => {
    return `<span class="hashtag-tag" onclick="event.stopPropagation(); loadCommunityFeedView('all', '', '${tag}')">#${tag}</span>`;
  });
  return escaped;
}

/* ==============================================================================
   REACTIONS & VOTING HANDLERS
   ============================================================================== */

function toggleReactionPicker(postId) {
  const popover = document.getElementById(`rx-popover-${postId}`);
  if (!popover) return;
  const isShown = popover.classList.contains("show");
  // Close all other popovers
  document.querySelectorAll(".reaction-popover").forEach(p => p.classList.remove("show"));
  if (!isShown) {
    popover.classList.add("show");
  }
}

// Close reaction popovers when clicking outside
document.addEventListener("click", (e) => {
  if (!e.target.closest(".reaction-wrapper")) {
    document.querySelectorAll(".reaction-popover").forEach(p => p.classList.remove("show"));
  }
});

async function submitPostReaction(postId, reactionKey) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }
  document.querySelectorAll(".reaction-popover").forEach(p => p.classList.remove("show"));

  try {
    const res = await apiRequest(`/api/posts/${postId}/react`, {
      method: "POST",
      body: JSON.stringify({ reaction: reactionKey })
    });

    // Update Main React button
    const wrapper = document.getElementById(`rx-wrapper-${postId}`);
    if (wrapper) {
      const btn = wrapper.querySelector(".rx-main-btn");
      const icon = wrapper.querySelector(".rx-btn-icon");
      const label = wrapper.querySelector(".rx-btn-label");

      if (res.user_reaction && REACTION_CONFIG[res.user_reaction]) {
        btn.classList.add("reacted");
        icon.textContent = REACTION_CONFIG[res.user_reaction].emoji;
        label.textContent = REACTION_CONFIG[res.user_reaction].name;
      } else {
        btn.classList.remove("reacted");
        icon.textContent = "❤️";
        label.textContent = "React";
      }
    }

    // Update Reaction Pills Row
    const pillsRow = document.getElementById(`rx-pills-${postId}`);
    if (pillsRow) {
      pillsRow.innerHTML = renderReactionPillsHtml(postId, res.reactions);
    }
  } catch (err) {
    showToast("Error updating reaction: " + err.message, "error");
  }
}

async function castPollVote(pollId, optionIndex) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }

  try {
    const res = await apiRequest(`/api/polls/${pollId}/vote`, {
      method: "POST",
      body: JSON.stringify({ option_index: optionIndex })
    });

    const pollEl = document.getElementById(`poll-card-${pollId}`);
    if (pollEl && res.poll) {
      pollEl.outerHTML = renderPollCard(res.poll);
    }
    showToast("Vote recorded!", "success");
  } catch (err) {
    showToast("Error voting: " + err.message, "error");
  }
}

async function deletePost(postId) {
  if (!confirm("Delete this post?")) return;
  try {
    await apiRequest(`/api/posts/${postId}`, { method: "DELETE" });
    showToast("Post deleted", "info");
    document.getElementById(`post-card-${postId}`)?.remove();
  } catch (err) {
    showToast("Error deleting post: " + err.message, "error");
  }
}

/* ==============================================================================
   COMMENTS & NESTED REPLIES
   ============================================================================== */

async function toggleCommentsDrawer(postId) {
  const container = document.getElementById(`comments-container-${postId}`);
  if (!container) return;

  if (container.style.display === "block") {
    container.style.display = "none";
    return;
  }

  container.style.display = "block";
  container.innerHTML = `<div style="text-align: center; color: var(--text-light); font-size: 0.85rem; padding: 0.5rem;">Loading comments...</div>`;

  try {
    const data = await apiRequest(`/api/posts/${postId}/comments`);
    renderCommentsSection(postId, data.comments || []);
  } catch (err) {
    container.innerHTML = `<div style="color: var(--danger); font-size: 0.85rem;">Failed to load comments</div>`;
  }
}

function renderCommentsSection(postId, comments) {
  const container = document.getElementById(`comments-container-${postId}`);
  if (!container) return;

  const commentsListHtml = comments.map(c => {
    const isOwner = currentUser && (currentUser.id === c.user_id || currentUser.is_admin === 1);
    const isReply = Boolean(c.parent_id);
    const badgesHtml = renderBadgesHtml(c.author_badges || []);

    return `
      <div class="comment-item ${isReply ? 'reply' : ''}" id="comment-${c.id}">
        <img src="${escapeHtml(c.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" style="width: 28px; height: 28px;" />
        <div class="comment-bubble">
          <div style="display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem; flex-wrap: wrap;">
            <div style="display: flex; align-items: center; gap: 0.35rem;">
              <span class="comment-author">@${escapeHtml(c.username)}</span>
              ${c.is_verified ? '<span title="Verified Chef">⭐</span>' : ''}
              ${badgesHtml}
            </div>
            <span style="font-size: 0.72rem; color: var(--text-light);">${formatRelativeTime(c.created_at)}</span>
          </div>
          <div class="comment-text">
            ${c.reply_to_username ? `<b style="color: var(--primary);">@${escapeHtml(c.reply_to_username)}</b> ` : ''}
            ${formatPostContent(c.comment)}
          </div>
          <div class="comment-meta">
            <span onclick="prepareCommentReply(${postId}, ${c.id}, '${escapeHtml(c.username)}')">Reply</span>
            <span onclick="openReportModal(null, ${c.id})">Report</span>
            ${isOwner ? `<span style="color: var(--danger);" onclick="deleteComment(${c.id})">Delete</span>` : ''}
          </div>
        </div>
      </div>
    `;
  }).join("");

  container.innerHTML = `
    <div class="comment-list" id="comment-list-${postId}">
      ${commentsListHtml || '<div style="color: var(--text-light); font-size: 0.85rem;">No comments yet. Start the discussion!</div>'}
    </div>
    <form class="comment-input-wrap" onsubmit="handleCommentSubmit(event, ${postId})">
      <input type="hidden" id="reply-parent-id-${postId}" value="" />
      <input type="hidden" id="reply-username-${postId}" value="" />
      <input type="text" id="comment-input-${postId}" class="form-control" style="font-size: 0.85rem;" placeholder="Write a comment... (Type @ to mention)" required oninput="handleMentionInput(this, 'comment-mention-popup-${postId}')" />
      <div id="comment-mention-popup-${postId}" class="mention-autocomplete-popup" style="display: none;"></div>
      <button type="submit" class="btn btn-primary btn-sm">Post</button>
    </form>
  `;
}

function prepareCommentReply(postId, parentId, username) {
  const input = document.getElementById(`comment-input-${postId}`);
  const parentIdInput = document.getElementById(`reply-parent-id-${postId}`);
  const usernameInput = document.getElementById(`reply-username-${postId}`);
  if (input && parentIdInput && usernameInput) {
    parentIdInput.value = parentId;
    usernameInput.value = username;
    input.placeholder = `Replying to @${username}...`;
    input.focus();
  }
}

async function handleCommentSubmit(e, postId) {
  e.preventDefault();
  if (!currentUser) {
    openAuthModal("login");
    return;
  }

  const input = document.getElementById(`comment-input-${postId}`);
  const parentIdInput = document.getElementById(`reply-parent-id-${postId}`);
  const usernameInput = document.getElementById(`reply-username-${postId}`);

  const comment = input.value.trim();
  const parent_id = parentIdInput.value ? parseInt(parentIdInput.value) : null;
  const reply_to_username = usernameInput.value || null;

  if (!comment) return;

  try {
    await apiRequest(`/api/posts/${postId}/comments`, {
      method: "POST",
      body: JSON.stringify({ comment, parent_id, reply_to_username })
    });
    input.value = "";
    parentIdInput.value = "";
    usernameInput.value = "";
    input.placeholder = "Write a comment...";
    const data = await apiRequest(`/api/posts/${postId}/comments`);
    renderCommentsSection(postId, data.comments || []);
  } catch (err) {
    showToast("Error adding comment: " + err.message, "error");
  }
}

async function deleteComment(commentId) {
  if (!confirm("Delete this comment?")) return;
  try {
    await apiRequest(`/api/comments/${commentId}`, { method: "DELETE" });
    showToast("Comment deleted", "info");
    document.getElementById(`comment-${commentId}`)?.remove();
  } catch (err) {
    showToast("Error deleting comment: " + err.message, "error");
  }
}

/* ==============================================================================
   CREATE POST MODAL & POLL CREATOR
   ============================================================================== */

function openCreateModal(defaultType = "post", defaultStationId = null, enablePoll = false) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }

  const modal = document.getElementById("create-post-modal");
  if (!modal) return;

  postUploadedImageUrl = "";
  document.getElementById("post-type-select").value = defaultType;
  document.getElementById("post-content-input").value = "";
  document.getElementById("post-image-file").value = "";
  document.getElementById("post-image-preview-wrap").style.display = "none";
  document.getElementById("post-image-preview").src = "";

  isPollEnabledInModal = enablePoll;
  const pollSection = document.getElementById("post-poll-builder-section");
  if (pollSection) {
    pollSection.style.display = enablePoll ? "block" : "none";
    document.getElementById("poll-question-input").value = "";
    document.getElementById("poll-option-1").value = "";
    document.getElementById("poll-option-2").value = "";
    document.getElementById("poll-option-3").value = "";
  }

  loadUserRecipesDropdown();
  loadStationsDropdown(defaultStationId);

  modal.classList.add("show");
}

function closeCreateModal() {
  const modal = document.getElementById("create-post-modal");
  if (modal) modal.classList.remove("show");
}

function togglePollBuilder() {
  isPollEnabledInModal = !isPollEnabledInModal;
  const pollSection = document.getElementById("post-poll-builder-section");
  if (pollSection) {
    pollSection.style.display = isPollEnabledInModal ? "block" : "none";
  }
}

async function loadStationsDropdown(preselectedStationId = null) {
  const select = document.getElementById("post-station-select");
  if (!select) return;

  try {
    const data = await apiRequest("/api/stations");
    const stations = data.stations || [];
    select.innerHTML = `<option value="">-- Kitchen Main Feed (No Station) --</option>` +
      stations.map(s => `
        <option value="${s.id}" ${preselectedStationId && preselectedStationId == s.id ? 'selected' : ''}>
          ${escapeHtml(s.icon || '🍳')} ${escapeHtml(s.name)} (station/${escapeHtml(s.slug)})
        </option>
      `).join("");
  } catch (err) {
    select.innerHTML = `<option value="">-- Kitchen Main Feed (No Station) --</option>`;
  }
}

async function loadUserRecipesDropdown() {
  const select = document.getElementById("post-recipe-select");
  if (!select) return;

  try {
    const data = await apiRequest("/api/recipes?scope=mine");
    select.innerHTML = `<option value="">-- No Recipe Attached --</option>` +
      (data.recipes || []).map(r => `<option value="${r.id}">${escapeHtml(r.title)}</option>`).join("");
  } catch (err) {
    select.innerHTML = `<option value="">-- No Recipe Attached --</option>`;
  }
}

async function handleImageFileSelected(e) {
  const file = e.target.files[0];
  if (!file) return;

  const preview = document.getElementById("post-image-preview");
  const wrap = document.getElementById("post-image-preview-wrap");

  try {
    showToast("Optimizing dish photo client-side...", "info", 1500);
    const blob = await downsampleImageFile(file, 1280, 1280);
    preview.src = URL.createObjectURL(blob);
    wrap.style.display = "block";

    const formData = new FormData();
    formData.append("image", blob, "upload.jpg");

    const res = await apiRequest("/api/upload", {
      method: "POST",
      body: formData
    });

    postUploadedImageUrl = res.url;
    showToast("Dish photo uploaded!", "success");
  } catch (err) {
    showToast("Upload failed: " + err.message, "error");
    wrap.style.display = "none";
  }
}

function downsampleImageFile(file, maxWidth, maxHeight) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = (event) => {
      const img = new Image();
      img.src = event.target.result;
      img.onload = () => {
        let width = img.width;
        let height = img.height;

        if (width > maxWidth || height > maxHeight) {
          if (width > height) {
            height = Math.round((height * maxWidth) / width);
            width = maxWidth;
          } else {
            width = Math.round((width * maxHeight) / height);
            height = maxHeight;
          }
        }

        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, width, height);

        canvas.toBlob(
          (blob) => {
            if (blob) resolve(blob);
            else reject(new Error("Canvas conversion failed"));
          },
          "image/jpeg",
          0.85
        );
      };
      img.onerror = reject;
    };
    reader.onerror = reject;
  });
}

async function handlePostCreateSubmit(e) {
  e.preventDefault();
  const content = document.getElementById("post-content-input").value.trim();
  const post_type = document.getElementById("post-type-select").value;
  const station_id = document.getElementById("post-station-select")?.value || null;
  const recipe_id = document.getElementById("post-recipe-select").value || null;

  if (!content) {
    showToast("Please enter post content", "error");
    return;
  }

  // Check attached poll
  let pollPayload = null;
  if (isPollEnabledInModal) {
    const pq = (document.getElementById("poll-question-input")?.value || "").trim();
    const opt1 = (document.getElementById("poll-option-1")?.value || "").trim();
    const opt2 = (document.getElementById("poll-option-2")?.value || "").trim();
    const opt3 = (document.getElementById("poll-option-3")?.value || "").trim();
    const opts = [opt1, opt2, opt3].filter(Boolean);

    if (pq && opts.length >= 2) {
      pollPayload = { question: pq, options: opts };
    }
  }

  try {
    await apiRequest("/api/posts", {
      method: "POST",
      body: JSON.stringify({
        content,
        post_type,
        station_id: station_id ? parseInt(station_id) : null,
        recipe_id: recipe_id ? parseInt(recipe_id) : null,
        image_url: postUploadedImageUrl,
        poll: pollPayload
      })
    });

    showToast("Post published to the culinary community!", "success");
    closeCreateModal();

    if (window.location.hash.startsWith("#station/") && typeof currentStationSlug !== "undefined" && currentStationSlug) {
      loadStationDetailView(currentStationSlug, currentStationFilter || "all");
    } else {
      loadCommunityFeedView("all");
    }
  } catch (err) {
    showToast("Error creating post: " + err.message, "error");
  }
}

/* ==============================================================================
   INTERACTIVE @MENTIONS AUTOCOMPLETE POPUP
   ============================================================================== */

let mentionSearchTimeout = null;

function handleMentionInput(inputEl, popupId) {
  const popup = document.getElementById(popupId);
  if (!popup) return;

  const val = inputEl.value;
  const cursor = inputEl.selectionStart;
  const textBefore = val.slice(0, cursor);
  const match = textBefore.match(/@([a-zA-Z0-9_]{1,20})$/);

  if (!match) {
    popup.style.display = "none";
    return;
  }

  const query = match[1];
  clearTimeout(mentionSearchTimeout);
  mentionSearchTimeout = setTimeout(async () => {
    try {
      const data = await apiRequest(`/api/users?q=${encodeURIComponent(query)}`);
      const users = (data.users || []).slice(0, 5);

      if (users.length === 0) {
        popup.style.display = "none";
        return;
      }

      popup.innerHTML = users.map(u => `
        <div class="mention-item" onclick="insertMention('${escapeHtml(u.username)}', '${inputEl.id}', '${popupId}')">
          <img src="${escapeHtml(u.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" style="width: 22px; height: 22px;" />
          <div>
            <span style="font-weight: 700; font-size: 0.85rem;">@${escapeHtml(u.username)}</span>
            <span style="font-size: 0.75rem; color: var(--text-light); margin-left: 0.35rem;">${escapeHtml(u.display_name)}</span>
          </div>
        </div>
      `).join("");
      popup.style.display = "block";
    } catch (e) {
      popup.style.display = "none";
    }
  }, 200);
}

function insertMention(username, inputId, popupId) {
  const input = document.getElementById(inputId);
  const popup = document.getElementById(popupId);
  if (!input) return;

  const val = input.value;
  const cursor = input.selectionStart;
  const textBefore = val.slice(0, cursor);
  const textAfter = val.slice(cursor);

  const updatedBefore = textBefore.replace(/@([a-zA-Z0-9_]{1,20})$/, `@${username} `);
  input.value = updatedBefore + textAfter;
  input.focus();
  input.setSelectionRange(updatedBefore.length, updatedBefore.length);

  if (popup) popup.style.display = "none";
}

/* ==============================================================================
   MODERATION REPORT MODAL
   ============================================================================== */

let reportingPostId = null;
let reportingCommentId = null;

function openReportModal(postId = null, commentId = null) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }

  reportingPostId = postId;
  reportingCommentId = commentId;

  const modal = document.getElementById("report-modal");
  if (!modal) return;
  modal.classList.add("show");
}

function closeReportModal() {
  const modal = document.getElementById("report-modal");
  if (modal) modal.classList.remove("show");
}

async function handleReportSubmit(e) {
  e.preventDefault();
  const reason = document.getElementById("report-reason-select").value;

  try {
    const data = await apiRequest("/api/reports", {
      method: "POST",
      body: JSON.stringify({
        post_id: reportingPostId,
        comment_id: reportingCommentId,
        reason
      })
    });
    showToast(data.message, "success");
    closeReportModal();
  } catch (err) {
    showToast("Error submitting report: " + err.message, "error");
  }
}

function formatRelativeTime(dateStr) {
  if (!dateStr) return "recently";
  const date = new Date(dateStr.replace(" ", "T") + "Z");
  const now = new Date();
  const diffSec = Math.floor((now - date) / 1000);

  if (diffSec < 60) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}
