/* ==============================================================================
   COOKED - Social Community Feed, Comments, Likes & Moderation
   ============================================================================== */

let currentFeedFilter = "all";
let openCommentsPostId = null;

async function loadCommunityFeedView(filter = "all") {
  currentFeedFilter = filter;
  const container = document.getElementById("main-content-view");
  if (!container) return;

  container.innerHTML = `
    <!-- Feed Filter Bar -->
    <div class="feed-filter-bar">
      <button class="filter-chip ${filter === 'all' ? 'active' : ''}" onclick="loadCommunityFeedView('all')">🔥 All Feed</button>
      <button class="filter-chip ${filter === 'question' ? 'active' : ''}" onclick="loadCommunityFeedView('question')">❓ Kitchen Questions</button>
      <button class="filter-chip ${filter === 'showcase' ? 'active' : ''}" onclick="loadCommunityFeedView('showcase')">📸 Dish Showcases</button>
      <button class="filter-chip ${filter === 'following' ? 'active' : ''}" onclick="loadCommunityFeedView('following')">👥 Following</button>
    </div>

    <!-- Create Post Card -->
    <div class="create-post-card">
      <div class="create-post-header">
        <img src="${escapeHtml(currentUser?.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" />
        <input type="text" class="form-control" style="border-radius: var(--radius-full); cursor: pointer;" placeholder="Share a culinary tip, ask a cooking question, or showcase your latest dish..." onclick="openCreateModal()" readonly />
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 0.5rem; border-top: 1px solid var(--border-subtle);">
        <div style="display: flex; gap: 0.75rem;">
          <button class="btn btn-secondary btn-sm" onclick="openCreateModal('showcase')">📸 Photo</button>
          <button class="btn btn-secondary btn-sm" onclick="openCreateModal('question')">❓ Ask Question</button>
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

  return `
    <div class="post-card" id="post-card-${post.id}">
      <div class="post-header">
        <div class="post-author-info">
          <img src="${escapeHtml(post.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" onclick="openUserProfile('${escapeHtml(post.username)}')" />
          <div>
            <div style="display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
              <span class="author-name" onclick="openUserProfile('${escapeHtml(post.username)}')">${escapeHtml(post.display_name || post.username)}</span>
              ${typeBadge}
              ${stationBadge}
            </div>
            <span class="author-username">@${escapeHtml(post.username)} • ${formatRelativeTime(post.created_at)}</span>
          </div>
        </div>
        <div style="display: flex; gap: 0.35rem;">
          <button class="btn-icon" title="Report" onclick="openReportModal(${post.id}, null)">🚩</button>
          ${isOwner ? `<button class="btn-icon" style="color: var(--danger);" title="Delete" onclick="deletePost(${post.id})">🗑️</button>` : ''}
        </div>
      </div>

      <div class="post-content">${escapeHtml(post.content)}</div>

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

      <div class="post-actions">
        <div class="action-group">
          <button class="post-action-btn ${post.is_liked ? 'liked' : ''}" onclick="toggleLikePost(${post.id}, this)">
            <svg style="width: 18px; height: 18px;" viewBox="0 0 24 24" fill="${post.is_liked ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
            </svg>
            <span class="like-count">${post.like_count || 0}</span>
          </button>
          <button class="post-action-btn" onclick="toggleCommentsDrawer(${post.id})">
            <svg style="width: 18px; height: 18px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
            </svg>
            <span>${post.comment_count || 0} Comments</span>
          </button>
        </div>
      </div>

      <!-- Comments Drawer Container -->
      <div id="comments-container-${post.id}" style="display: none;" class="comments-section"></div>
    </div>
  `;
}

async function toggleLikePost(postId, btnEl) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }
  const isLiked = btnEl.classList.contains("liked");
  const method = isLiked ? "DELETE" : "POST";
  try {
    const data = await apiRequest(`/api/posts/${postId}/like`, { method });
    if (data.is_liked) {
      btnEl.classList.add("liked");
      btnEl.querySelector("svg").setAttribute("fill", "currentColor");
    } else {
      btnEl.classList.remove("liked");
      btnEl.querySelector("svg").setAttribute("fill", "none");
    }
    btnEl.querySelector(".like-count").textContent = data.like_count;
  } catch (err) {
    showToast("Error updating like: " + err.message, "error");
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
    return `
      <div class="comment-item ${isReply ? 'reply' : ''}" id="comment-${c.id}">
        <img src="${escapeHtml(c.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" style="width: 28px; height: 28px;" />
        <div class="comment-bubble">
          <div style="display: flex; justify-content: space-between; align-items: baseline;">
            <span class="comment-author">@${escapeHtml(c.username)}</span>
            <span style="font-size: 0.72rem; color: var(--text-light);">${formatRelativeTime(c.created_at)}</span>
          </div>
          <div class="comment-text">
            ${c.reply_to_username ? `<b style="color: var(--primary);">@${escapeHtml(c.reply_to_username)}</b> ` : ''}
            ${escapeHtml(c.comment)}
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
      <input type="text" id="comment-input-${postId}" class="form-control" style="font-size: 0.85rem;" placeholder="Write a comment..." required />
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
    // Reload comments
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
   CREATE POST MODAL WITH CLIENT-SIDE CANVAS DOWNSAMPLING
   ============================================================================== */

let postUploadedImageUrl = "";

function openCreateModal(defaultType = "post", defaultStationId = null) {
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

  // Load user's recipes for attachment dropdown
  loadUserRecipesDropdown();

  // Load kitchen stations dropdown
  loadStationsDropdown(defaultStationId);

  modal.classList.add("show");
}

function closeCreateModal() {
  const modal = document.getElementById("create-post-modal");
  if (modal) modal.classList.remove("show");
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

/**
 * Downsample image via HTML5 Canvas (max 1280x1280 JPEG) before uploading
 */
async function handleImageFileSelected(e) {
  const file = e.target.files[0];
  if (!file) return;

  const preview = document.getElementById("post-image-preview");
  const wrap = document.getElementById("post-image-preview-wrap");

  try {
    showToast("Downsampling image client-side for fast upload...", "info", 1500);
    const blob = await downsampleImageFile(file, 1280, 1280);
    preview.src = URL.createObjectURL(blob);
    wrap.style.display = "block";

    // Upload to server
    const formData = new FormData();
    formData.append("image", blob, "upload.jpg");

    const res = await apiRequest("/api/upload", {
      method: "POST",
      body: formData
    });

    postUploadedImageUrl = res.url;
    showToast("Dish photo processed & uploaded!", "success");
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

  try {
    await apiRequest("/api/posts", {
      method: "POST",
      body: JSON.stringify({
        content,
        post_type,
        station_id: station_id ? parseInt(station_id) : null,
        recipe_id: recipe_id ? parseInt(recipe_id) : null,
        image_url: postUploadedImageUrl
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
