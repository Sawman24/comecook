/* ==============================================================================
   COOKED - Media Lightbox for High-Resolution Dish Photos
   ============================================================================== */

function openLightbox(imageUrl, caption = "") {
  let overlay = document.getElementById("lightbox-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "lightbox-overlay";
    overlay.className = "lightbox-overlay";
    overlay.innerHTML = `
      <button class="lightbox-close" id="lightbox-close-btn" aria-label="Close image">✕</button>
      <div style="text-align: center; max-width: 90vw;">
        <img class="lightbox-img" id="lightbox-img" src="" alt="Dish Photo" />
        <p id="lightbox-caption" style="color: #fff; margin-top: 10px; font-size: 0.95rem;"></p>
      </div>
    `;
    document.body.appendChild(overlay);

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay || e.target.id === "lightbox-close-btn") {
        closeLightbox();
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && overlay.classList.contains("show")) {
        closeLightbox();
      }
    });
  }

  const img = document.getElementById("lightbox-img");
  const cap = document.getElementById("lightbox-caption");
  img.src = imageUrl;
  cap.textContent = caption;

  overlay.classList.add("show");
  document.body.style.overflow = "hidden";
}

function closeLightbox() {
  const overlay = document.getElementById("lightbox-overlay");
  if (overlay) {
    overlay.classList.remove("show");
    document.body.style.overflow = "";
  }
}
