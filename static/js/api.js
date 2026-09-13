/* ==============================================================================
   COOKED - API Client & Core Utilities
   ============================================================================== */

/**
 * Escape HTML to neutralize XSS vectors.
 */
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Toast Notification System
 */
function showToast(message, type = "info", duration = 3500) {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span>${escapeHtml(message)}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

/**
 * Core Fetch Wrapper with JSON handling and Cookie credentials
 */
async function apiRequest(endpoint, options = {}) {
  const defaultHeaders = {
    "Content-Type": "application/json",
    "Accept": "application/json"
  };

  // Attach Bearer token from localStorage for seamless cross-protocol / reverse proxy support
  const storedToken = localStorage.getItem("cooked_auth_token");
  if (storedToken) {
    defaultHeaders["Authorization"] = `Bearer ${storedToken}`;
  }

  // If body is FormData or not provided, delete Content-Type
  if (options.body instanceof FormData || !options.body) {
    delete defaultHeaders["Content-Type"];
  }

  const config = {
    ...options,
    credentials: "same-origin",
    headers: {
      ...defaultHeaders,
      ...(options.headers || {})
    }
  };


  try {
    const response = await fetch(endpoint, config);
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      const errorMsg = data.message || data.error || `HTTP error ${response.status}`;
      throw new Error(errorMsg);
    }

    return data;
  } catch (err) {
    console.error(`API Error [${endpoint}]:`, err);
    throw err;
  }
}

/**
 * Downsample and optimize an image file client-side before upload.
 */
function downsampleImageFile(file, maxWidth = 1280, maxHeight = 1280) {
  return new Promise((resolve, reject) => {
    if (!file || !file.type.startsWith("image/")) {
      return reject(new Error("Selected file is not an image"));
    }
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
      img.onerror = () => reject(new Error("Could not decode image file"));
    };
    reader.onerror = () => reject(new Error("Failed to read image file"));
  });
}

/**
 * Upload an image with automatic client-side optimization and raw file fallback.
 */
async function uploadImageFile(file) {
  let uploadBlob = file;
  try {
    if (typeof downsampleImageFile === "function") {
      uploadBlob = await downsampleImageFile(file, 1280, 1280);
    }
  } catch (downsampleErr) {
    console.warn("Client downsample fallback to raw file:", downsampleErr);
    uploadBlob = file;
  }

  const formData = new FormData();
  formData.append("image", uploadBlob, file.name || "dish.jpg");

  const res = await apiRequest("/api/upload", {
    method: "POST",
    body: formData
  });

  if (!res || !res.url) {
    throw new Error(res?.message || "Upload failed");
  }
  return res.url;
}

/**
 * Convert Date object to local YYYY-MM-DD string without UTC timezone shift.
 */
function formatLocalDate(d = new Date()) {
  const dateObj = (d instanceof Date && !isNaN(d.getTime())) ? d : new Date();
  const year = dateObj.getFullYear();
  const month = String(dateObj.getMonth() + 1).padStart(2, "0");
  const day = String(dateObj.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/**
 * Format timestamp into human-readable relative time (e.g., 'just now', '5m ago', '2h ago', '3d ago').
 */
function formatTimeAgo(timestamp) {
  if (!timestamp) return "";
  try {
    let clean = String(timestamp).trim();
    if (!clean.includes("Z") && !clean.includes("+") && !/-\d\d:\d\d$/.test(clean)) {
      clean = clean.replace(" ", "T") + "Z";
    }
    const date = new Date(clean);
    if (isNaN(date.getTime())) return timestamp;
    const now = new Date();
    const diffSeconds = Math.max(0, Math.floor((now - date) / 1000));

    if (diffSeconds < 60) return "just now";
    const minutes = Math.floor(diffSeconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    const months = Math.floor(days / 30);
    if (months < 12) return `${months}mo ago`;
    return `${Math.floor(days / 365)}y ago`;
  } catch (e) {
    return timestamp;
  }
}

/**
 * Alias for formatTimeAgo with fallback to "recently".
 */
function formatRelativeTime(dateStr) {
  const res = formatTimeAgo(dateStr);
  return res || "recently";
}


