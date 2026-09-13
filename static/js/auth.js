/* ==============================================================================
   COOKED - Authentication & Profile Manager
   ============================================================================== */

let currentUser = null;

async function checkAuthStatus() {
  try {
    const data = await apiRequest("/api/auth/me");
    currentUser = data.user || null;
    updateAuthUI();
    return currentUser;
  } catch (err) {
    currentUser = null;
    updateAuthUI();
    return null;
  }
}

function updateAuthUI() {
  const container = document.getElementById("nav-auth-container");
  const adminNav = document.getElementById("admin-nav-section");

  if (adminNav) {
    adminNav.style.display = (currentUser && currentUser.is_admin === 1) ? "block" : "none";
  }

  if (!container) return;

  if (currentUser) {
    container.innerHTML = `
      <div style="display: flex; align-items: center; gap: 0.75rem;">
        <button class="btn btn-outline btn-sm" onclick="openCreateModal()">
          <span style="font-size: 1.1rem; line-height: 1;">+</span> Share
        </button>
        <div style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;" onclick="openUserProfile('${escapeHtml(currentUser.username)}')">
          <img src="${escapeHtml(currentUser.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100')}" class="avatar-sm" alt="${escapeHtml(currentUser.username)}" />
          <div style="display: flex; flex-direction: column; line-height: 1.1;">
            <span style="font-weight: 700; font-size: 0.85rem;">${escapeHtml(currentUser.display_name)}</span>
            <span style="font-size: 0.75rem; color: var(--text-light);">@${escapeHtml(currentUser.username)}${currentUser.is_admin ? ' <b style="color:var(--primary);">[Admin]</b>' : ''}</span>
          </div>
        </div>
        <button class="btn-icon" title="Logout" onclick="handleLogout()">
          <svg style="width: 18px; height: 18px; stroke: currentColor; fill: none;" viewBox="0 0 24 24" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
        </button>
      </div>
    `;
  } else {
    container.innerHTML = `
      <div style="display: flex; gap: 0.5rem;">
        <button class="btn btn-secondary btn-sm" onclick="openAuthModal('login')">Log In</button>
        <button class="btn btn-primary btn-sm" onclick="openAuthModal('register')">Sign Up</button>
      </div>
    `;
  }
}

function openAuthModal(mode = "login") {
  const modal = document.getElementById("auth-modal");
  if (!modal) return;

  const isLogin = mode === "login";
  const isRegister = mode === "register";
  const isForgot = mode === "forgot";

  const titleEl = document.getElementById("auth-modal-title");
  const bodyEl = document.getElementById("auth-modal-form");

  if (isLogin) {
    titleEl.textContent = "Welcome Back to Cooked";
    bodyEl.innerHTML = `
      <form onsubmit="handleLoginSubmit(event)">
        <div class="form-group">
          <label>Username or Email</label>
          <input type="text" id="auth-username" class="form-control" required autocomplete="username" placeholder="e.g. marco_pasta or email@domain.com" />
        </div>
        <div class="form-group">
          <label>Password</label>
          <input type="password" id="auth-password" class="form-control" required autocomplete="current-password" placeholder="••••••••" />
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem;">
          <a href="javascript:void(0)" onclick="openAuthModal('forgot')" style="font-size: 0.82rem;">Forgot password?</a>
        </div>
        <button type="submit" class="btn btn-primary" style="width: 100%;">Log In</button>
        <p style="text-align: center; margin-top: 1rem; font-size: 0.85rem; color: var(--text-muted);">
          Don't have an account? <a href="javascript:void(0)" onclick="openAuthModal('register')">Sign up</a>
        </p>
      </form>
    `;
  } else if (isRegister) {
    titleEl.textContent = "Join the Cooked Community";
    bodyEl.innerHTML = `
      <form onsubmit="handleRegisterSubmit(event)">
        <div class="form-group">
          <label>Username</label>
          <input type="text" id="reg-username" class="form-control" required placeholder="chef_gordon" minlength="3" maxlength="30" autocomplete="username" />
        </div>
        <div class="form-group">
          <label>Display Name</label>
          <input type="text" id="reg-display" class="form-control" required placeholder="Gordon Ramsay" maxlength="50" />
        </div>
        <div class="form-group">
          <label>Email Address</label>
          <input type="email" id="reg-email" class="form-control" required placeholder="chef@example.com" autocomplete="email" />
        </div>
        <div class="form-group">
          <label>Password</label>
          <input type="password" id="reg-password" class="form-control" required minlength="8" placeholder="Create a strong password" autocomplete="new-password" oninput="evaluatePasswordStrength(this.value, 'reg-pw-feedback')" />
          <div id="reg-pw-feedback" class="password-feedback-container">
            <div class="password-strength-wrap">
              <div class="password-strength-bar"><div class="password-strength-fill" id="reg-pw-fill"></div></div>
              <span class="password-strength-text" id="reg-pw-text">Password strength</span>
            </div>
            <div class="password-reqs-grid">
              <span class="password-req-item" id="req-len">○ 8+ Characters</span>
              <span class="password-req-item" id="req-upper">○ Uppercase (A-Z)</span>
              <span class="password-req-item" id="req-lower">○ Lowercase (a-z)</span>
              <span class="password-req-item" id="req-num">○ Number (0-9)</span>
              <span class="password-req-item" id="req-sym">○ Special Symbol (!@#$)</span>
            </div>
          </div>
        </div>
        <div class="form-group">
          <label>Culinary Bio (Optional)</label>
          <textarea id="reg-bio" class="form-control" placeholder="What's your favorite cuisine or cooking philosophy?"></textarea>
        </div>
        <button type="submit" class="btn btn-primary" style="width: 100%;">Create Account</button>
        <p style="text-align: center; margin-top: 1rem; font-size: 0.85rem; color: var(--text-muted);">
          Already have an account? <a href="javascript:void(0)" onclick="openAuthModal('login')">Log in</a>
        </p>
      </form>
    `;
  } else {
    titleEl.textContent = "Reset Your Password";
    bodyEl.innerHTML = `
      <form onsubmit="handleForgotSubmit(event)">
        <div class="form-group">
          <label>Email Address</label>
          <input type="email" id="forgot-email" class="form-control" required placeholder="Enter registered email" />
        </div>
        <button type="submit" class="btn btn-primary" style="width: 100%;">Generate Reset Token</button>
        <p style="text-align: center; margin-top: 1rem; font-size: 0.85rem;">
          <a href="javascript:void(0)" onclick="openAuthModal('login')">Back to Login</a>
        </p>
      </form>
    `;
  }

  modal.classList.add("show");
}

function evaluatePasswordStrength(password, containerId) {
  const hasLen = password.length >= 8;
  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasNum = /[0-9]/.test(password);
  const hasSym = /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?~`]/.test(password);

  const prefix = containerId === "reg-pw-feedback" ? "req-" : "reset-req-";
  const lenEl = document.getElementById(`${prefix}len`);
  const upperEl = document.getElementById(`${prefix}upper`);
  const lowerEl = document.getElementById(`${prefix}lower`);
  const numEl = document.getElementById(`${prefix}num`);
  const symEl = document.getElementById(`${prefix}sym`);

  if (lenEl) { lenEl.className = `password-req-item ${hasLen ? 'met' : ''}`; lenEl.textContent = `${hasLen ? '✓' : '○'} 8+ Characters`; }
  if (upperEl) { upperEl.className = `password-req-item ${hasUpper ? 'met' : ''}`; upperEl.textContent = `${hasUpper ? '✓' : '○'} Uppercase (A-Z)`; }
  if (lowerEl) { lowerEl.className = `password-req-item ${hasLower ? 'met' : ''}`; lowerEl.textContent = `${hasLower ? '✓' : '○'} Lowercase (a-z)`; }
  if (numEl) { numEl.className = `password-req-item ${hasNum ? 'met' : ''}`; numEl.textContent = `${hasNum ? '✓' : '○'} Number (0-9)`; }
  if (symEl) { symEl.className = `password-req-item ${hasSym ? 'met' : ''}`; symEl.textContent = `${hasSym ? '✓' : '○'} Special Symbol (!@#$)`; }

  const score = [hasLen, hasUpper, hasLower, hasNum, hasSym].filter(Boolean).length;
  const fillPrefix = containerId === "reg-pw-feedback" ? "reg-pw-" : "reset-pw-";
  const fillEl = document.getElementById(`${fillPrefix}fill`);
  const textEl = document.getElementById(`${fillPrefix}text`);

  if (fillEl && textEl) {
    if (!password) {
      fillEl.style.width = "0%";
      fillEl.style.backgroundColor = "transparent";
      textEl.textContent = "Password strength";
      textEl.style.color = "var(--text-light)";
    } else if (score <= 2) {
      fillEl.style.width = "30%";
      fillEl.style.backgroundColor = "var(--danger)";
      textEl.textContent = "Weak password";
      textEl.style.color = "var(--danger)";
    } else if (score === 3 || score === 4) {
      fillEl.style.width = "70%";
      fillEl.style.backgroundColor = "var(--warning)";
      textEl.textContent = "Moderate password";
      textEl.style.color = "var(--warning)";
    } else {
      fillEl.style.width = "100%";
      fillEl.style.backgroundColor = "var(--success)";
      textEl.textContent = "Strong culinary password ✓";
      textEl.style.color = "var(--success)";
    }
  }

  return score === 5;
}

function closeAuthModal() {
  const modal = document.getElementById("auth-modal");
  if (modal) modal.classList.remove("show");
}

async function handleLoginSubmit(e) {
  e.preventDefault();
  const username = document.getElementById("auth-username").value;
  const password = document.getElementById("auth-password").value;

  try {
    const data = await apiRequest("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password })
    });
    currentUser = data.user;
    updateAuthUI();
    closeAuthModal();
    showToast(`Welcome back, Chef ${currentUser.display_name}!`, "success");
    // Refresh current view
    if (typeof refreshCurrentView === "function") refreshCurrentView();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function handleRegisterSubmit(e) {
  e.preventDefault();
  const username = document.getElementById("reg-username").value.trim();
  const display_name = document.getElementById("reg-display").value.trim();
  const email = document.getElementById("reg-email").value.trim();
  const password = document.getElementById("reg-password").value;
  const bio = document.getElementById("reg-bio").value.trim();

  // Pre-validate password requirements on client
  const isStrong = evaluatePasswordStrength(password, "reg-pw-feedback");
  if (!isStrong) {
    showToast("Password must meet all 5 security requirements (8+ chars, upper, lower, number, symbol)", "error");
    return;
  }

  try {
    const data = await apiRequest("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, display_name, email, password, bio })
    });
    currentUser = data.user;
    updateAuthUI();
    closeAuthModal();
    showToast(`Welcome to Cooked, Chef ${currentUser.display_name}!`, "success");
    if (typeof refreshCurrentView === "function") refreshCurrentView();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function handleForgotSubmit(e) {
  e.preventDefault();
  const email = document.getElementById("forgot-email").value;
  try {
    const data = await apiRequest("/api/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email })
    });
    if (data.dev_reset_token) {
      showToast("Reset token generated! (Dev Fallback)", "info");
      // Present token reset form
      promptResetPassword(data.dev_reset_token);
    } else {
      showToast(data.message, "success");
      closeAuthModal();
    }
  } catch (err) {
    showToast(err.message, "error");
  }
}

function promptResetPassword(token) {
  const titleEl = document.getElementById("auth-modal-title");
  const bodyEl = document.getElementById("auth-modal-form");
  titleEl.textContent = "Set New Strong Password";
  bodyEl.innerHTML = `
    <form onsubmit="handleResetPasswordSubmit(event, '${token}')">
      <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">
        Reset token verified. Enter your new password below:
      </p>
      <div class="form-group">
        <label>New Password</label>
        <input type="password" id="reset-new-password" class="form-control" required minlength="8" placeholder="Enter new strong password" oninput="evaluatePasswordStrength(this.value, 'reset-pw-feedback')" />
        <div id="reset-pw-feedback" class="password-feedback-container">
          <div class="password-strength-wrap">
            <div class="password-strength-bar"><div class="password-strength-fill" id="reset-pw-fill"></div></div>
            <span class="password-strength-text" id="reset-pw-text">Password strength</span>
          </div>
          <div class="password-reqs-grid">
            <span class="password-req-item" id="reset-req-len">○ 8+ Characters</span>
            <span class="password-req-item" id="reset-req-upper">○ Uppercase (A-Z)</span>
            <span class="password-req-item" id="reset-req-lower">○ Lowercase (a-z)</span>
            <span class="password-req-item" id="reset-req-num">○ Number (0-9)</span>
            <span class="password-req-item" id="reset-req-sym">○ Special Symbol (!@#$)</span>
          </div>
        </div>
      </div>
      <button type="submit" class="btn btn-primary" style="width: 100%;">Update Password</button>
    </form>
  `;
}

async function handleResetPasswordSubmit(e, token) {
  e.preventDefault();
  const new_password = document.getElementById("reset-new-password").value;
  try {
    const data = await apiRequest("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password })
    });
    showToast(data.message, "success");
    openAuthModal("login");
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function handleLogout() {
  try {
    await apiRequest("/api/auth/logout", { method: "POST" });
    currentUser = null;
    updateAuthUI();
    showToast("You have been logged out.", "info");
    if (typeof refreshCurrentView === "function") refreshCurrentView();
  } catch (err) {
    showToast("Logout error: " + err.message, "error");
  }
}
