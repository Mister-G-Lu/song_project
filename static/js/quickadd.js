/**
 * quickadd.js - Quick-add songs you discover
 * FAB button + modal form + keyboard shortcut
 */

let quickAddSongCount = 0;

function openQuickAdd(prefillTitle) {
    const overlay = document.getElementById('quickAddOverlay');
    overlay.classList.add('active');
    
    if (prefillTitle) {
        document.getElementById('qaTitle').value = prefillTitle;
    }
    
    document.getElementById('qaTitle').focus();
    document.body.style.overflow = 'hidden';
}

function closeQuickAdd() {
    const overlay = document.getElementById('quickAddOverlay');
    overlay.classList.remove('active');
    document.body.style.overflow = '';
    
    // Reset form after animation
    setTimeout(() => {
        document.getElementById('quickAddForm').style.display = '';
        document.getElementById('qaSuccess').style.display = 'none';
    }, 300);
}

function resetQuickAddForm() {
    document.getElementById('quickAddForm').reset();
    document.getElementById('quickAddForm').style.display = '';
    document.getElementById('qaSuccess').style.display = 'none';
    document.getElementById('qaSubmitBtn').disabled = false;
    document.getElementById('qaSubmitBtn').textContent = 'Add Song';
    document.getElementById('qaTitle').focus();
}

async function submitQuickAdd(event) {
    event.preventDefault();
    
    const title = document.getElementById('qaTitle').value.trim();
    const rating = document.getElementById('qaRating').value.trim();
    const notes = document.getElementById('qaNotes').value.trim();
    const source = document.getElementById('qaSource').value;
    
    if (!title) {
        showToast('Please enter a song title');
        return;
    }
    
    const submitBtn = document.getElementById('qaSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Checking for duplicates...';
    
    // Check if this song already exists (O(1) hash lookup on server)
    try {
        const checkResp = await fetch('/api/check-song', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: title })
        });
        const checkData = await checkResp.json();
        if (checkData.exists) {
            const confirmed = confirm(
                `This song appears to already be in your collection!\n\n` +
                `Title: "${title}"\n` +
                `Match: ${checkData.match || 'similar title'}\n\n` +
                `Do you still want to add it? (It will create a duplicate entry.)`
            );
            if (!confirmed) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Add Song';
                return;
            }
        }
    } catch (e) {
        // Duplicate check is nice-to-have; proceed even if it fails
        console.warn('Duplicate check failed:', e);
    }
    
    // Build the notes with source info
    let fullNotes = notes;
    if (source && !fullNotes.includes(source)) {
        fullNotes = fullNotes ? `${fullNotes} [Found via: ${source}]` : `[Found via: ${source}]`;
    }
    
    try {
        const resp = await fetch('/api/add-song', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: title,
                rating: rating || '',
                notes: fullNotes
            })
        });
        
        const data = await resp.json();
        
        if (data.success) {
            quickAddSongCount++;
            document.getElementById('quickAddForm').style.display = 'none';
            document.getElementById('qaSuccess').style.display = 'block';
            
            // Refresh dashboard stats if visible
            const statTotal = document.getElementById('statTotal');
            if (statTotal && statTotal.textContent !== '-') {
                const current = parseInt(statTotal.textContent.replace(/,/g, '')) || 0;
                statTotal.textContent = (current + 1).toLocaleString();
            }
            
            // Refresh recent reviews if visible
            const recentContainer = document.getElementById('recentReviews');
            if (recentContainer && recentContainer.querySelector('.review-item')) {
                fetch('/api/stats')
                    .then(r => r.json())
                    .then(d => {
                        if (d.recent_reviews && window.renderRecentReviews) {
                            renderRecentReviews(d.recent_reviews);
                        }
                    })
                    .catch(() => {});
            }
            
            // Auto-refresh the source view so saved song disappears from Challenge/Rec
            // Only refresh if the view is still active (user didn't navigate away)
            if (source === 'recommender' || source === 'challenge') {
                setTimeout(() => {
                    const viewEl = document.getElementById('view-' + source);
                    if (!viewEl || !viewEl.classList.contains('active')) return;
                    if (source === 'recommender' && window.loadRecommender) {
                        loadRecommender();
                    } else if (source === 'challenge' && window.loadChallenges) {
                        loadChallenges();
                    }
                }, 500);
            }
            
            showToast(`Added "${title.split('(')[0].trim()}" to your collection!`);
        } else {
            showToast(data.error || 'Failed to add song');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Add Song';
        }
    } catch (err) {
        showToast('Connection error. Check that the server is running.');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Add Song';
    }
}

// Export for use from recommender cards
function quickAddFromRecommender(artist, song, source) {
    const title = `${artist} – ${song}`;
    document.getElementById('qaSource').value = source || 'recommender';
    openQuickAdd(title);
}

// Keyboard shortcut: press 'A' to open quick-add; Escape to close
document.addEventListener('keydown', function(e) {
    const overlay = document.getElementById('quickAddOverlay');
    // Escape must work even when focus is in a form field (adversarial review finding)
    if (e.key === 'Escape' && overlay.classList.contains('active')) {
        closeQuickAdd();
        return;
    }
    // A / A key only when not typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
        return;
    }
    if (e.key === 'a' || e.key === 'A') {
        if (!overlay.classList.contains('active')) {
            openQuickAdd();
            e.preventDefault();
        }
    }
});

// Export for use from recommender cards
function quickAddFromRecommender(artist, song) {
    const title = `${artist} – ${song}`;
    document.getElementById('qaSource').value = 'recommender';
    openQuickAdd(title);
}
