<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Master Schedule | Neat & Necessary</title>
    
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>

    <style>
        /* --- 1. GLOBAL VARIABLES & RESET --- */
        :root {
            --bg-body: #09090b;       /* Ultra Dark Background */
            --bg-panel: #18181b;      /* Panel Background */
            --bg-hover: #27272a;      /* Hover State */
            --border: #27272a;        /* Subtle Borders */
            --text-main: #e4e4e7;     /* High Contrast Text */
            --text-muted: #a1a1aa;    /* Secondary Text */
            --primary: #22c55e;       /* Brand Green */
            --primary-glow: rgba(34, 197, 94, 0.15);
            --danger: #ef4444;        /* Red */
            --radius: 8px;            /* Standard curvature */
        }

        * { box-sizing: border-box; }

        /* Scope specifically to Admin Root to avoid breaking Webflow nav */
        #admin-root {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-body);
            color: var(--text-main);
            height: 85vh; /* Adjusted for Webflow embedding */
            min-height: 600px;
            overflow: hidden; 
            display: flex;
            border: 1px solid var(--border);
            border-radius: 12px;
            position: relative;
            z-index: 10;
        }

        /* --- 2. SIDEBAR (FILTERS & GROUPS) --- */
        .app-sidebar {
            width: 280px;
            background: var(--bg-panel);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
            z-index: 20;
        }

        .sidebar-header {
            padding: 24px;
            border-bottom: 1px solid var(--border);
        }

        .brand-title {
            font-size: 16px;
            font-weight: 700;
            letter-spacing: -0.02em;
            display: flex;
            align-items: center;
            gap: 10px;
            color: white;
        }
        .brand-dot { width: 8px; height: 8px; background: var(--primary); border-radius: 50%; box-shadow: 0 0 8px var(--primary); }

        .sidebar-content {
            flex: 1;
            padding: 24px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        /* Filter Sections */
        .filter-section-title {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            font-weight: 600;
            margin-bottom: 12px;
        }

        .custom-select {
            width: 100%;
            background: var(--bg-body);
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 10px 12px;
            border-radius: var(--radius);
            font-size: 13px;
            outline: none;
            transition: border-color 0.2s;
            cursor: pointer;
        }
        .custom-select:focus { border-color: var(--primary); }

        /* Staff List Visuals */
        .staff-list { display: flex; flex-direction: column; gap: 4px; }
        .staff-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.15s;
        }
        .staff-item:hover { background: var(--bg-hover); }
        .staff-avatar {
            width: 24px; height: 24px;
            border-radius: 6px;
            display: flex; align-items: center; justify-content: center;
            font-size: 10px; font-weight: 700; color: white;
        }
        .staff-name { font-size: 13px; color: var(--text-main); }
        .staff-status { width: 6px; height: 6px; border-radius: 50%; background: var(--border); margin-left: auto; }
        .staff-item.active .staff-status { background: var(--primary); }

        /* --- 3. MAIN WORKSPACE --- */
        .app-main {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-width: 0; /* Flexbox safety */
            background: var(--bg-body);
        }

        /* Top Toolbar */
        .toolbar {
            height: 64px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 24px;
            background: rgba(9, 9, 11, 0.8);
            backdrop-filter: blur(8px);
            position: sticky;
            top: 0;
            z-index: 10;
        }

        .date-navigator {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .nav-icon-btn {
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-main);
            width: 32px; height: 32px;
            border-radius: 6px;
            cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            transition: all 0.2s;
        }
        .nav-icon-btn:hover { background: var(--bg-hover); border-color: var(--text-muted); }

        .current-range {
            font-size: 15px;
            font-weight: 600;
        }

        .primary-btn {
            background: var(--primary);
            color: #000;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            transition: opacity 0.2s;
        }
        .primary-btn:hover { opacity: 0.9; }

        /* Calendar Grid */
        .calendar-container {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }

        .grid-header {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 1px;
            margin-bottom: 10px;
        }
        .day-label {
            text-align: center;
            font-size: 13px;
            font-weight: 500;
            color: var(--text-muted);
            padding-bottom: 8px;
        }
        .day-label.today { color: var(--primary); font-weight: 700; }

        .main-grid {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 8px;
        }

        .day-column {
            background: var(--bg-panel);
            border: 1px solid var(--border);
            border-radius: 8px;
            min-height: 400px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            transition: border-color 0.2s;
        }
        .day-column:hover { border-color: #3f3f46; }

        .day-col-header {
            padding: 12px;
            font-size: 13px;
            font-weight: 600;
            text-align: center;
            border-bottom: 1px solid var(--border);
            background: rgba(255,255,255,0.02);
        }
        .day-col-body {
            flex: 1;
            padding: 8px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        /* Click target for adding shifts */
        .day-col-body:hover { cursor: crosshair; }

        /* Shift Cards */
        .shift-pill {
            background: #27272a;
            border-left: 3px solid var(--text-muted);
            padding: 8px 10px;
            border-radius: 4px;
            cursor: pointer;
            transition: transform 0.1s, filter 0.1s;
            position: relative;
            overflow: hidden;
        }
        .shift-pill {
    transition: transform 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.2s;
}

.shift-pill:hover {
    transform: scale(1.05);
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 0 10px var(--primary-glow);
    z-index: 50;
    filter: brightness(1.1);
}

.shift-pill:active {
    transform: scale(0.95);
}
        
        .pill-time { font-size: 11px; font-weight: 700; color: var(--text-main); display: block; margin-bottom: 2px;}
        .pill-name { font-size: 12px; color: var(--text-muted); }
        .pill-loc { 
            position: absolute; top: 4px; right: 4px; 
            font-size: 9px; padding: 2px 4px; background: rgba(0,0,0,0.3); border-radius: 3px; 
            text-transform: uppercase; font-weight: 600; opacity: 0.7;
        }

        /* --- 4. MODAL --- */
        .modal-backdrop {
            display: none;
            position: fixed; inset: 0;
            background: rgba(0,0,0,0.6);
            backdrop-filter: blur(4px);
            z-index: 100;
            align-items: center; justify-content: center;
        }
        .modal-card {
            background: #18181b;
            border: 1px solid #3f3f46;
            width: 400px;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
            animation: modalPop 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes modalPop { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); }}

        .modal-title { font-size: 18px; font-weight: 600; margin: 0 0 20px 0; color: white; }
        
        .form-group { margin-bottom: 16px; }
        .form-label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 6px; font-weight: 500; }
        .form-input {
            width: 100%; background: #09090b; border: 1px solid var(--border);
            color: white; padding: 10px; border-radius: 6px; font-size: 14px; outline: none;
        }
        .form-input:focus { border-color: var(--primary); }

        .modal-actions { display: flex; gap: 10px; margin-top: 24px; }
        .btn-full { flex: 1; height: 40px; }
        .btn-outline { background: transparent; border: 1px solid var(--danger); color: var(--danger); }
        .btn-outline:hover { background: rgba(239, 68, 68, 0.1); }
    </style>
</head>
<body>

<div id="admin-root">
    <div class="app-sidebar">
        <div class="sidebar-header">
            <div class="brand-title">
                <div class="brand-dot"></div>
                Admin Console
            </div>
        </div>

        <div class="sidebar-content">
            <div>
                <div class="filter-section-title">Filter by Location</div>
                <select id="filterArea" class="custom-select">
                    <option value="ALL">All Service Areas</option>
                    <option value="Billings">Billings</option>
                    <option value="Bozeman">Bozeman</option>
                    <option value="Missoula">Missoula</option>
                </select>
            </div>

            <div>
                <div class="filter-section-title">Filter by Staff</div>
                <select id="filterCleaner" class="custom-select">
                    <option value="ALL">All Cleaners</option>
                </select>
            </div>

<div>
    <div class="filter-section-title">Job Status</div>
    <select id="filterJobStatus" class="custom-select">
        <option value="ALL">Show All Jobs</option>
        <option value="UNASSIGNED">Unassigned Only</option>
        <option value="ASSIGNED">Assigned Only</option>
        <option value="CONFLICT">Conflicts Only</option>
    </select>
</div>

            <div>
                <div class="filter-section-title" style="margin-top:20px;">Active Roster</div>
                <div id="staffListContainer" class="staff-list">
                    </div>
            </div>
        </div>
    </div>

    <div class="app-main">
        <div class="toolbar">
            <div class="date-navigator">
                <button class="nav-icon-btn" id="prevBtn" title="Previous Week">&larr;</button>
                <button class="nav-icon-btn" id="todayBtn">T</button>
                <button class="nav-icon-btn" id="nextBtn" title="Next Week">&rarr;</button>
<div style="margin-left: 12px; display: flex; gap: 4px; background: var(--bg-panel); padding: 4px; border-radius: 6px; border: 1px solid var(--border);">
    <button class="primary-btn" id="viewWeek" style="padding: 4px 12px; font-size: 11px;">Week</button>
    <button class="primary-btn" id="viewMonth" style="padding: 4px 12px; font-size: 11px; background: transparent; color: var(--text-muted);">Month</button>
</div>
                <span class="current-range" id="dateLabel">Loading...</span>
            </div>
            
            <div>
                <button class="primary-btn" onclick="openModal()">+ Add Shift</button>
            </div>
        </div>

        <div class="calendar-container">
            <div class="grid-header" id="headerRow"></div>
            
            <div class="main-grid" id="mainGrid"></div>
        </div>
    </div>

	<div class="modal-backdrop" id="detailModal" style="display:none; align-items: center; justify-content: center;">
    <div class="modal-card" style="width: 500px; transform: scale(1.1); border: 1px solid var(--primary);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px;">
            <h2 id="detailTitle" style="margin: 0; color: var(--primary);">Shift Details</h2>
            <button class="nav-icon-btn" onclick="closeDetailModal()">✕</button>
        </div>
        
        <div id="detailContent" style="display: flex; flex-direction: column; gap: 16px;">
            <div class="form-group">
                <label class="form-label">Cleaner</label>
                <div id="viewCleaner" style="font-size: 18px; font-weight: 700;"></div>
            </div>
            
            <div style="display: flex; gap: 24px;">
                <div class="form-group">
                    <label class="form-label">Date</label>
                    <div id="viewDate" style="font-size: 16px;"></div>
                </div>
                <div class="form-group">
                    <label class="form-label">Time</label>
                    <div id="viewTime" style="font-size: 16px;"></div>
                </div>
            </div>

            <div class="form-group">
                <label class="form-label">Service Area</label>
                <div id="viewArea" style="font-size: 16px; display: flex; align-items: center; gap: 8px;"></div>
            </div>
        </div>

        <div class="modal-actions" style="margin-top: 32px;">
            <button class="primary-btn btn-full" id="editFromDetail">Edit Shift</button>
            <button class="primary-btn btn-full btn-outline" onclick="closeDetailModal()">Close</button>
        </div>
    </div>
</div>

    <div class="modal-backdrop" id="scheduleModal">
        <div class="modal-card">
            <h3 class="modal-title" id="modalTitle">Manage Shift</h3>
            <input type="hidden" id="slotId">
            
            <div class="form-group">
                <label class="form-label">Team Member</label>
                <select id="modalCleaner" class="form-input"></select>
            </div>

            <div class="form-group">
                <label class="form-label">Date</label>
                <input type="date" id="modalDate" class="form-input">
            </div>

            <div style="display:flex; gap:12px;">
                <div class="form-group" style="flex:1;">
                    <label class="form-label">Start Time</label>
                    <select id="modalStart" class="form-input"></select>
                </div>
                <div class="form-group" style="flex:1;">
                    <label class="form-label">End Time</label>
                    <select id="modalEnd" class="form-input"></select>
                </div>
            </div>

            <div class="form-group">
                <label class="form-label">Service Area</label>
                <select id="modalArea" class="form-input">
                    <option value="">No Area Assigned</option>
                    <option value="Billings">Billings</option>
                    <option value="Bozeman">Bozeman</option>
                    <option value="Missoula">Missoula</option>
                </select>
            </div>

            <div class="modal-actions">
                <button class="primary-btn btn-full" id="saveBtn">Save Changes</button>
                <button class="primary-btn btn-full btn-outline" id="deleteBtn" style="display:none;">Delete</button>
                <button class="nav-icon-btn" style="width:40px;" onclick="closeModal()">✕</button>
            </div>



        </div>
    </div>
</div>

<script>
    // --- WEBFLOW DUPLICATE PROTECTION ---
    // This check stops the script if Webflow tries to load it twice
    if (window.adminCalendarInit) {
        console.log("Admin Calendar already initialized. Skipping duplicate load.");
    } else {
        window.adminCalendarInit = true;

        // --- 1. CONFIGURATION ---
        const CONFIG = {
            SUPABASE_URL: "https://rfdvogakvyodixgpvqvz.supabase.co", 
            SUPABASE_KEY: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJmZHZvZ2FrdnlvZGl4Z3B2cXZ6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjcwMzU4MDMsImV4cCI6MjA4MjYxMTgwM30.UumTuz6AaKL8uYmmNxFj1ec5CInHVNQowt6LRo4cu-E".trim()
        };

        // Reuse connection if it exists, otherwise create new
        window.adminSupabase = window.adminSupabase || window.supabase.createClient(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_KEY);
        const supabase = window.adminSupabase;
        
        // --- STATE ---
        // Declare globally at the top of the script
window.staffMap = window.staffMap || {};
let staffMap = window.staffMap;
window.allShifts = window.allShifts || [];
let currentDate = new Date();
let currentView = 'week'; // Default view
        const colors = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#22c55e', '#06b6d4'];

        // --- INIT ---
        async function initApp() {
            generateTimeOptions();
            renderCalendarSkeleton(); 
            
            // Listeners
            
            document.getElementById('prevBtn').onclick = () => currentView === 'week' ? jumpDate(-7) : jumpMonth(-1);
document.getElementById('nextBtn').onclick = () => currentView === 'week' ? jumpDate(7) : jumpMonth(1);

document.getElementById('viewWeek').onclick = () => switchView('week');
document.getElementById('viewMonth').onclick = () => switchView('month');

function jumpMonth(val) {
    currentDate.setMonth(currentDate.getMonth() + val);
    refreshUI();
}

function switchView(view) {
    currentView = view;
    document.getElementById('viewWeek').style.background = view === 'week' ? 'var(--primary)' : 'transparent';
    document.getElementById('viewWeek').style.color = view === 'week' ? '#000' : 'var(--text-muted)';
    document.getElementById('viewMonth').style.background = view === 'month' ? 'var(--primary)' : 'transparent';
    document.getElementById('viewMonth').style.color = view === 'month' ? '#000' : 'var(--text-muted)';
    refreshUI();
}
            document.getElementById('todayBtn').onclick = () => { currentDate = new Date(); refreshUI(); };
            document.getElementById('filterArea').onchange = refreshUI;
            document.getElementById('filterCleaner').onchange = refreshUI;
document.getElementById('filterJobStatus').onchange = refreshUI;
            
            document.getElementById('saveBtn').onclick = saveShift;
            document.getElementById('deleteBtn').onclick = deleteShift;

            // Load Data
            await loadData();
        }

        // --- DATA ---
window.loadData = async function loadData() {
    const supabase = window.adminSupabase;
    const [availRes, assignRes, jobsRes] = await Promise.all([
    supabase.from('cleaner_availability_time_slots').select('*'),
    supabase
        .from('job_assignments')
        .select(`
            *,
            jobs (
                job_id,
                first_name,
                last_name,
                service_area,
                scheduled_start,
                price
            )
        `),
    supabase.from('jobs').select('*') // keep temporarily for safety
]);


    if(availRes.error || jobsRes.error || assignRes.error) return console.error("Data Fetch Error");
    
    window.allShifts = availRes.data || [];
   window.allAssignments = assignRes.data || [];

// 🔑 jobs now come FROM assignments
window.allJobs = window.allAssignments
    .filter(a => a.jobs)
    .map(a => ({
        ...a.jobs,
        assignments: window.allAssignments.filter(x => x.job_id === a.job_id)
    }));

    
    processStaff(window.allShifts);
    populateAssignCleanerSelect(); 
    refreshUI();
}

        function processStaff(data) {
    window.staffMap = {}; // Update the global reference
    staffMap = window.staffMap;
            const filterSelect = document.getElementById('filterCleaner');
            const modalSelect = document.getElementById('modalCleaner');
            const listContainer = document.getElementById('staffListContainer');

            filterSelect.innerHTML = '<option value="ALL">All Cleaners</option>';
            modalSelect.innerHTML = '<option value="" disabled selected>Select Staff...</option>';
            listContainer.innerHTML = '';

            let colorIdx = 0;
            // 1. Get names from current shifts
            let shiftNames = data.map(d => d.user_name).filter(n => n);
            
            // 2. Add "Master List" (Melissa, Sara, etc.) to ensure they always show up
            const masterList = ["Melissa Cook", "Sara Smith", "Aaron Parker"];
            const names = [...new Set([...shiftNames, ...masterList])].sort();

            names.forEach(name => {
                const color = colors[colorIdx % colors.length];
                const initials = name.split(' ').map(n=>n[0]).join('').substring(0,2).toUpperCase();
                const userRow = data.find(d => d.user_name === name);
                const uid = userRow ? userRow.user_id : null;

                staffMap[name] = { id: uid, color, initials };
                colorIdx++;

                filterSelect.add(new Option(name, name));
                modalSelect.add(new Option(name, name));

                const item = document.createElement('div');
                item.className = 'staff-item';
                item.innerHTML = `
                    <div class="staff-avatar" style="background:${color}">${initials}</div>
                    <span class="staff-name">${name}</span>
                    <div class="staff-status"></div>
                `;
                item.onclick = () => {
                    filterSelect.value = name;
                    refreshUI();
                };
                listContainer.appendChild(item);
            });
        }

        // --- RENDERING ---
      function refreshUI() {
    const grid = document.getElementById('mainGrid');
    const headerRow = document.getElementById('headerRow');
    if(!grid || !headerRow) return;

    grid.innerHTML = '';
    headerRow.innerHTML = '';

    const areaFilter = document.getElementById('filterArea').value;
    const staffFilter = document.getElementById('filterCleaner').value;
const jobStatusFilter = document.getElementById('filterJobStatus').value;

    let startDate, totalDays;

    if (currentView === 'week') {
        startDate = getStartOfWeek(new Date(currentDate));
        totalDays = 7;
        grid.style.gridTemplateColumns = 'repeat(7, 1fr)';
        const endOfWeek = new Date(startDate);
        endOfWeek.setDate(startDate.getDate() + 6);
        document.getElementById('dateLabel').innerText = `${formatDate(startDate)} - ${formatDate(endOfWeek)}`;
    } else {
        // Month View Logic
        const firstDayOfMonth = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
        startDate = getStartOfWeek(firstDayOfMonth); // Start on the Sunday before the 1st
        totalDays = 42; // standard 6-week grid
        grid.style.gridTemplateColumns = 'repeat(7, 1fr)';
        document.getElementById('dateLabel').innerText = currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    }

    // Render Headers (Sun - Sat)
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    days.forEach(d => {
        const th = document.createElement('div');
        th.className = 'day-label';
        th.innerText = d;
        headerRow.appendChild(th);
    });

    for(let i=0; i < totalDays; i++) {
        const day = new Date(startDate);
        day.setDate(startDate.getDate() + i);
        const dateKey = day.toISOString().split('T')[0];
        const isToday = new Date().toDateString() === day.toDateString();
        const isCurrentMonth = day.getMonth() === currentDate.getMonth();

        const col = document.createElement('div');
        col.className = 'day-column';
        col.style.minHeight = currentView === 'week' ? '400px' : '120px'; // Shrink cells for month view
        if(!isCurrentMonth && currentView === 'month') col.style.opacity = '0.3';
        if(isToday) col.style.borderColor = 'var(--primary)';

        col.innerHTML = `
            <div class="day-col-header" style="padding: 4px; font-size: 11px;">${day.getDate()}</div>
            <div class="day-col-body" id="col-${dateKey}" style="gap: 2px; padding: 4px;"></div>
        `;
        
        col.querySelector('.day-col-body').onclick = (e) => {
            if(e.target === e.currentTarget) openModal(null, dateKey);
        };

        grid.appendChild(col);
        const container = col.querySelector('.day-col-body');
        
        const shifts = window.allShifts.filter(s => {
            if(s.date !== dateKey) return false;
            if(areaFilter !== "ALL" && s.service_area !== areaFilter) return false;
            if(staffFilter !== "ALL" && s.user_name !== staffFilter) return false;
            return true;
        });

        shifts.sort((a,b) => a.start_time.localeCompare(b.start_time));

        shifts.forEach(shift => {
            const meta = (window.staffMap && window.staffMap[shift.user_name]) ? window.staffMap[shift.user_name] : { color: '#555', initials: '??' };
            const pill = document.createElement('div');
            pill.className = 'shift-pill';
            pill.style.borderLeftColor = meta.color;
            pill.style.padding = currentView === 'week' ? '8px 10px' : '2px 4px';
            
            const area = shift.service_area || "";
            const locCode = area ? area.substring(0,3).toUpperCase() : "";

            pill.innerHTML = `
                <span class="pill-time" style="font-size: ${currentView === 'week' ? '11px' : '9px'}">${formatTime(shift.start_time)}</span>
                <span class="pill-name" style="font-size: ${currentView === 'week' ? '12px' : '10px'}">${currentView === 'week' ? shift.user_name : meta.initials}</span>
                ${(locCode && currentView === 'week') ? `<span class="pill-loc" style="color:${meta.color}">${locCode}</span>` : ''}
            `;
            
            pill.onclick = (e) => {
                e.stopPropagation();
                openDetailModal(shift);
            };
            container.appendChild(pill);
        });

        // --- 2. RENDER JOBS ---
        const jobs = (window.allJobs || []).filter(j => {
    if (!j.scheduled_start) return false;

    const jobDate = j.scheduled_start.split('T')[0];
    if (jobDate !== dateKey) return false;
    if (areaFilter !== "ALL" && j.service_area !== areaFilter) return false;

    const assignments = j.assignments || [];
    const isAssigned = assignments.length > 0;

    let hasConflict = false;
    if (isAssigned) {
        hasConflict = assignments.some(a => {
            const cleanerName = Object.keys(window.staffMap)
                .find(name => window.staffMap[name].id === a.cleaner_id);

            return !window.allShifts.some(
                s => s.user_name === cleanerName && s.date === jobDate
            );
        });
    }

    if (jobStatusFilter === "UNASSIGNED" && isAssigned) return false;
    if (jobStatusFilter === "ASSIGNED" && !isAssigned) return false;
    if (jobStatusFilter === "CONFLICT" && !hasConflict) return false;

    return true;
});


            

            jobs.forEach(job => {
    const assignments = (window.allAssignments || []).filter(
        a => a.job_id === job.job_id
    );

    const isAssigned = assignments.length > 0;
    const jobDate = job.scheduled_start.split('T')[0];

    let hasConflict = false;
    if (isAssigned) {
        hasConflict = assignments.some(a => {
            const cleanerName = Object.keys(window.staffMap)
                .find(name => window.staffMap[name].id === a.cleaner_id);

            return !window.allShifts.some(
                s => s.user_name === cleanerName && s.date === jobDate
            );
        });
    }

    const pill = document.createElement('div');
    pill.className = 'shift-pill';
    pill.style.background = '#000';
    pill.style.border = `1px solid ${
        hasConflict ? '#f59e0b' : (isAssigned ? 'var(--primary)' : 'var(--danger)')
    }`;
    pill.style.borderLeft = `4px solid ${
        hasConflict ? '#f59e0b' : (isAssigned ? 'var(--primary)' : 'var(--danger)')
    }`;

    pill.innerHTML = `
        <span class="pill-time" style="color:white; font-weight:800;">
            ${hasConflict ? '⚠️ CONFLICT' : 'JOB'}
        </span>
        <span class="pill-name" style="color:white;">
            ${job.first_name} ${job.last_name}
        </span>
        <div class="pill-loc" style="
            background:${hasConflict ? '#f59e0b' : (isAssigned ? 'var(--primary)' : 'var(--danger)')};
            color:black;
            opacity:1;
            font-weight:bold;
            top:2px;
            right:2px;
        ">
            ${assignments.length} CLEANER${assignments.length !== 1 ? 'S' : ''}
        </div>
    `;

    pill.onclick = (e) => {
        e.stopPropagation();
        openJobAssignmentModal(job);
    };

    container.appendChild(pill);
});

    } // This brace closes the for-loop of days
} // This brace closes the refreshUI function

   


        // --- MODAL LOGIC ---
        const modal = document.getElementById('scheduleModal');

        function openModal(shift = null, dateKey = null) {
            window.currentModalShift = shift; // Track what we are editing
            const title = document.getElementById('modalTitle');
            const delBtn = document.getElementById('deleteBtn');

            if(shift) {
                title.innerText = "Edit Shift";
                delBtn.style.display = 'block';
                document.getElementById('slotId').value = shift.id;
                document.getElementById('modalCleaner').value = shift.user_name;
                document.getElementById('modalDate').value = shift.date;
                document.getElementById('modalStart').value = shift.start_time.slice(0,5);
                document.getElementById('modalEnd').value = shift.end_time.slice(0,5);
               // This ensures that if the shift has an area (like Missoula), the dropdown selects it correctly
document.getElementById('modalArea').value = shift.service_area || "";
            } else {
                title.innerText = "Add New Shift";
                delBtn.style.display = 'none';
                document.getElementById('slotId').value = "";
                document.getElementById('modalDate').value = dateKey || new Date().toISOString().split('T')[0];
                document.getElementById('modalStart').value = "09:00";
                document.getElementById('modalEnd').value = "17:00";
            }
            modal.style.display = 'flex';
        }

        window.closeModal = function() { modal.style.display = 'none'; }

        // --- DATABASE ACTIONS ---
        async function saveShift() {
            const id = document.getElementById('slotId').value;
            const name = document.getElementById('modalCleaner').value;
            const date = document.getElementById('modalDate').value;
            const start = document.getElementById('modalStart').value;
            const end = document.getElementById('modalEnd').value;
            const area = document.getElementById('modalArea').value;

            if(!name || !date) return alert("Please select staff and date.");

            const meta = staffMap[name];
            const payload = {
                user_name: name,
                user_id: meta ? meta.id : null, 
                date: date, 
                start_time: start, 
                end_time: end, 
                service_area: area // Ensures "Missoula" is saved to the row
            };

            if(id) {
                await supabase.from('cleaner_availability_time_slots').update(payload).eq('id', id);
            } else {
                await supabase.from('cleaner_availability_time_slots').insert([payload]);
            }
            
            closeModal();
            loadData(); 
        }

        async function deleteShift() {
            const id = document.getElementById('slotId').value;
            if(confirm("Are you sure you want to remove this shift?")) {
                await supabase.from('cleaner_availability_time_slots').delete().eq('id', id);
                closeModal();
                loadData();
            }
        }

        // --- UTILS ---
        function getStartOfWeek(d) {
            const day = d.getDay();
            const diff = d.getDate() - day; 
            return new Date(d.setDate(diff));
        }
        function jumpDate(days) {
            currentDate.setDate(currentDate.getDate() + days);
            refreshUI();
        }
        function formatDate(d) { return d.toLocaleDateString('en-US', {month:'short', day:'numeric'}); }
        function formatTime(t) {
            if(!t) return "";
            let [h, m] = t.split(':');
            h = parseInt(h);
            const ampm = h >= 12 ? 'p' : 'a';
            h = h % 12 || 12;
            return `${h}${ampm}`;
        }
        function generateTimeOptions() {
            const s = document.getElementById('modalStart');
            const e = document.getElementById('modalEnd');
            for(let i=6; i<=22; i++) {
                const val = i < 10 ? `0${i}:00` : `${i}:00`;
                const label = formatTime(val);
                s.add(new Option(label, val)); e.add(new Option(label, val));
            }
        }
        function renderCalendarSkeleton() { refreshUI(); }

        // --- START ---
        initApp();
    }

function openDetailModal(shift) {
    const detailModal = document.getElementById('detailModal');
    
    // Safety check: ensure staffMap exists before accessing
    const currentStaffMap = window.staffMap || staffMap || {};
    const meta = currentStaffMap[shift.user_name] || { color: '#555', initials: '??' };
    
    // ... rest of your existing code
    
    // Fill data
    document.getElementById('viewCleaner').innerText = shift.user_name;
    document.getElementById('viewCleaner').style.color = meta.color;
    document.getElementById('viewDate').innerText = new Date(shift.date).toLocaleDateString('en-US', { 
        weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' 
    });
    document.getElementById('viewTime').innerText = `${formatTime(shift.start_time)} to ${formatTime(shift.end_time)}`;
    
    const area = shift.service_area || "Not Assigned";
    document.getElementById('viewArea').innerHTML = `
        <span style="background: ${meta.color}22; color: ${meta.color}; padding: 4px 12px; border-radius: 20px; border: 1px solid ${meta.color}; font-weight: 700;">
            ${area}
        </span>
    `;

    // Link Edit Button
    document.getElementById('editFromDetail').onclick = () => {
        closeDetailModal();
        openModal(shift);
    };

    detailModal.style.display = 'flex';
}

function closeDetailModal() {
    document.getElementById('detailModal').style.display = 'none';
}

// --- JOB ASSIGNMENT & CONFLICT LOGIC ---
function openJobAssignmentModal(job) {
    // Fill Primary Hidden ID
    document.getElementById('assignJobId').value = job.job_id;


    // Populate Job Detail Grid
    document.getElementById('assignJobCustomer').innerText = `${job.first_name || ''} ${job.last_name || ''}`;
    document.getElementById('assignJobArea').innerText = job.service_area || 'Not Assigned';
    document.getElementById('assignJobPrice').innerText = job.price ? `$${job.price}` : '$0.00';
    
    // Format Start Time
    if (job.scheduled_start) {
        const timePart = job.scheduled_start.split('T')[1];
        document.getElementById('assignJobStart').innerText = formatTime(timePart);
    } else {
        document.getElementById('assignJobStart').innerText = 'TBD';
    }

    // Set Status Badge
    const badge = document.getElementById('jobStatusBadge');
    // Get assignments for this job
const assignments = (window.allAssignments || []).filter(
  a => a.job_id === job.job_id
);

const isAssigned = assignments.length > 0;

    badge.innerText = isAssigned ? 'ASSIGNED' : 'UNASSIGNED';
badge.style.background = isAssigned ? 'var(--primary)' : 'var(--danger)';
badge.style.color = 'black';


    // Handle Cleaner Selection
    const select = document.getElementById('assignCleanerSelect');
    const warning = document.getElementById('conflictWarning');
    warning.style.display = 'none';

   // Preselect first assigned cleaner (if any)
if (assignments.length > 0) {
    const first = assignments[0];
    const name = Object.keys(window.staffMap)
        .find(n => window.staffMap[n].id === first.cleaner_id);

    select.value = name || "";
} else {
    select.value = "";
}


    // Conflict detection logic
    select.onchange = () => {
        const selectedName = select.value;
        if (!selectedName) { warning.style.display = 'none'; return; }
        
        const jobDate = job.scheduled_start.split('T')[0];
        const hasAvail = window.allShifts.some(s => 
            s.user_name === selectedName && 
            s.date === jobDate
        );
        warning.style.display = hasAvail ? 'none' : 'block';
    };

    document.getElementById('jobAssignmentModal').style.display = 'flex';
}

// --- JOB ASSIGNMENT & MODAL CONTROL ---

/**
 * Saves the job assignment by updating the 'crew_id' in Supabase.
 * It maps the human-readable cleaner name back to their staff ID.
 */
async function saveJobAssignment() {
    const jobId = document.getElementById('assignJobId').value;
    const cleanerName = document.getElementById('assignCleanerSelect').value;
    const pType = document.getElementById('payoutType').value;
    const pValue = document.getElementById('payoutValue').value;

    if (!jobId || !cleanerName || !pValue) {
        alert("Please select a cleaner and payout amount.");
        return;
    }

    const cleanerId = window.staffMap[cleanerName]?.id;

    // Save to the new job_assignments table
    const { error } = await window.adminSupabase
        .from('job_assignments')
        .upsert({ 
            job_id: jobId, 
            cleaner_id: cleanerId,
            payout_type: pType,
            payout_value: parseFloat(pValue)
        }, { onConflict: 'job_id,cleaner_id' });

    if (error) {
        console.error("Save Error:", error.message);
        alert("Failed to save assignment.");
        return;
    }

    document.getElementById('jobAssignmentModal').style.display = 'none';
    await loadData(); // Reload everything
}


/**
 * Simply hides the assignment modal without saving.
 */
function closeAssignmentModal() {
    document.getElementById('jobAssignmentModal').style.display = 'none';
}


function populateAssignCleanerSelect() {
    const select = document.getElementById('assignCleanerSelect');
    if (!select) return;

    select.innerHTML = '<option value="">-- Unassigned (Available) --</option>';

    Object.keys(window.staffMap).forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
    });
}

</script>

<div class="modal-backdrop" id="jobAssignmentModal" style="display:none; align-items: center; justify-content: center;">
    <div class="modal-card" style="border: 1px solid var(--primary); width: 450px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h3 class="modal-title" style="margin: 0;">Job Assignment</h3>
            <span id="jobStatusBadge" style="font-size: 10px; padding: 4px 8px; border-radius: 4px; font-weight: bold;"></span>
        </div>
        
        <input type="hidden" id="assignJobId">
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px; background: var(--bg-body); padding: 15px; border-radius: 8px; border: 1px solid var(--border);">
            <div>
                <label class="form-label" style="margin-bottom: 2px;">Customer</label>
                <div id="assignJobCustomer" style="font-weight: 600; color: white; font-size: 15px;"></div>
            </div>
            <div>
                <label class="form-label" style="margin-bottom: 2px;">Service Area</label>
                <div id="assignJobArea" style="font-weight: 600; color: white; font-size: 15px;"></div>
            </div>
            <div>
                <label class="form-label" style="margin-bottom: 2px;">Start Time</label>
                <div id="assignJobStart" style="font-weight: 600; color: white; font-size: 15px;"></div>
            </div>
            <div>
                <label class="form-label" style="margin-bottom: 2px;">Job Price</label>
                <div id="assignJobPrice" style="font-weight: 700; color: var(--primary); font-size: 16px;"></div>
            </div>
        </div>


<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px;">
            <div class="form-group" style="margin-bottom:0;">
                <label class="form-label">Payout Type</label>
                <select id="payoutType" class="form-input">
                    <option value="PERCENT">Percent (%)</option>
                    <option value="FLAT">Flat Rate ($)</option>
                </select>
            </div>
            <div class="form-group" style="margin-bottom:0;">
                <label class="form-label">Payout Amount</label>
                <input type="number" id="payoutValue" class="form-input" placeholder="e.g. 50">
            </div>
        </div>

        <div class="form-group">
            <label class="form-label">Assign to Cleaner</label>
            <select id="assignCleanerSelect" class="form-input" style="border-color: var(--primary);">
                <option value="">-- Unassigned (Available) --</option>
            </select>
        </div>

        <div id="conflictWarning" style="display:none; margin-top: 10px; padding: 10px; background: rgba(245, 158, 11, 0.1); border: 1px solid #f59e0b; border-radius: 6px; font-size: 12px; color: #f59e0b;">
            ⚠️ <strong>Conflict:</strong> This cleaner hasn't posted availability for this date.
        </div>

        <div class="modal-actions" style="margin-top: 25px;">
            <button class="primary-btn btn-full" onclick="saveJobAssignment()">Save Assignment</button>
            <button class="nav-icon-btn" style="width:40px;" onclick="closeAssignmentModal()">✕</button>
        </div>
    </div>
</div>
</body>
</html>
