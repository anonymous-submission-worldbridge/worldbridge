'use strict';
(() => {
  const dialog = document.querySelector('#lightbox');
  let previousFocus;
  document.querySelectorAll('[data-lightbox]').forEach(link => {
    link.addEventListener('click', event => {
      event.preventDefault();
      previousFocus = link;
      const title = link.dataset.title;
      const image = document.querySelector('#lightbox-image');
      image.src = link.dataset.lightbox;
      image.alt = title;
      document.querySelector('#lightbox-title').textContent = title;
      document.querySelector('#lightbox-download').href = image.src;
      dialog.showModal();
    });
  });
  document.querySelector('#lightbox-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => previousFocus?.focus());
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  });
  const videos = [...document.querySelectorAll('video')];
  videos.forEach(video => video.addEventListener('play', () => {
    videos.forEach(other => { if (other !== video) other.pause(); });
  }));
})();
