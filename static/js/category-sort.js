// category-sort.js — client-side sort for category verdict grids
(function(){
  'use strict';
  const grid = document.getElementById('verdictGrid');
  if (!grid) return;

  const cards = Array.from(grid.querySelectorAll('.vg-card'));
  if (cards.length < 2) return;

  // Extract metadata from each card
  const items = cards.map(function(card, idx) {
    const titleLink = card.querySelector('.vg-title-link');
    const name = titleLink ? titleLink.textContent.trim().toLowerCase() : '';
    const stars = card.querySelector('.rating-inline');
    const summary = card.querySelector('.vg-summary');
    const reviewText = card.querySelector('.vg-review-count');
    return {
      idx: idx,
      card: card,
      name: name,
      rating: stars ? parseFloat(stars.textContent) || 0 : 0,
      reviews: reviewText ? parseInt(reviewText.textContent.replace(/[^0-9]/g, '')) || 0 : 0,
      summaryText: summary ? summary.textContent.trim().toLowerCase() : ''
    };
  });

  // Build sort controls
  const container = grid.parentElement;
  const controls = document.createElement('div');
  controls.className = 'category-sort-bar';
  controls.innerHTML = '<label class="sort-label">Sort by:</label>'
    + '<select class="sort-select"><option value="name-asc">Name A–Z</option>'
    + '<option value="rating-desc" selected>Highest Rated</option>'
    + '<option value="reviews-desc">Most Reviewed</option>'
    + '<option value="name-desc">Name Z–A</option></select>'
    + '<span class="sort-count">' + cards.length + ' products</span>';
  grid.parentElement.insertBefore(controls, grid);

  const select = controls.querySelector('.sort-select');

  function sortAndRender(mode) {
    var sorted;
    switch(mode) {
      case 'name-asc':
        sorted = items.slice().sort(function(a,b){ return a.name.localeCompare(b.name); });
        break;
      case 'name-desc':
        sorted = items.slice().sort(function(a,b){ return b.name.localeCompare(a.name); });
        break;
      case 'rating-desc':
        sorted = items.slice().sort(function(a,b){ return b.rating - a.rating; });
        break;
      case 'reviews-desc':
        sorted = items.slice().sort(function(a,b){ return b.reviews - a.reviews; });
        break;
      default:
        sorted = items.slice().sort(function(a,b){ return b.rating - a.rating; });
    }
    // Re-append in sorted order
    sorted.forEach(function(item){ grid.appendChild(item.card); });
  }

  select.addEventListener('change', function(e){ sortAndRender(e.target.value); });

  // Default sort: highest rated
  sortAndRender('rating-desc');
})();
