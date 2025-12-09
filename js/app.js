/**
 * Routes Départementales
 * Interactive map visualization with MapLibre GL JS + PMTiles
 */

import { LayerSwitcher, Layer, LayerGroup } from 'https://esm.sh/@russss/maplibregl-layer-switcher@2.1.0';


class RoadsMapApp {
    constructor() {
        // Map configuration
        this.map = null;
        this.centerCoords = [2.5, 46.5]; // [lng, lat] Metropolitan France center
        this.initialZoom = 6;

        // Data storage
        this.roadsIndex = null;

        // State
        this.selectedRoad = null;
        this.isLoading = false;

        // DOM elements
        this.elements = {
            deptSelect: document.getElementById('dept-select'),
            roadSelect: document.getElementById('road-select'),
            loading: document.getElementById('loading'),
            statsPanel: document.getElementById('stats-panel'),
            errorMessage: document.getElementById('error-message'),
            statRef: document.getElementById('stat-ref'),
            statLength: document.getElementById('stat-length'),
            clearBtn: document.getElementById('clear-selection'),
            sidebarToggle: document.getElementById('sidebar-toggle'),
            sidebar: document.querySelector('.sidebar')
        };

        // Choices.js instances
        this.deptChoices = null;
        this.roadChoices = null;

        // State
        this.selectedDept = null;

        // Colors
        this.colors = {
            selected: '#FF5722',
            variant: '#FF8A65',
            hover: '#FFA726'
        };

        // Layer switcher instance
        this.layerSwitcher = null;

        // Color ramp based on total road length (blue=short, red=long)
        this.lengthColorRamp = [
            'interpolate',
            ['linear'],
            ['get', 'total_length_km'],
            15, '#2196F3',   // Blue for short roads (<=15km)
            40, '#9C27B0',   // Purple for medium
            70, '#F44336'    // Red for long roads (>=70km)
        ];

        // Initialize
        this.init();
    }

    /**
     * Initialize the application
     */
    async init() {
        try {
            this.initChoices();
            await this.loadRoadsIndex();
            this.initMap();
            this.setupEventListeners();
            this.setupMobileToggle();
        } catch (error) {
            this.showError('Erreur lors de l\'initialisation: ' + error.message);
            console.error('Initialization error:', error);
        }
    }

    /**
     * Initialize Choices.js for searchable dropdowns
     */
    initChoices() {
        this.deptChoices = new Choices(this.elements.deptSelect, {
            searchEnabled: true,
            searchPlaceholderValue: 'Rechercher un département...',
            itemSelectText: '',
            shouldSort: false,
            placeholder: true,
            placeholderValue: 'Tous les départements',
            searchResultLimit: 100,
            noResultsText: 'Aucun résultat',
            noChoicesText: 'Aucun choix disponible'
        });

        this.roadChoices = new Choices(this.elements.roadSelect, {
            searchEnabled: true,
            searchPlaceholderValue: 'Rechercher une route...',
            itemSelectText: '',
            shouldSort: false,
            placeholder: true,
            placeholderValue: 'Toutes les routes',
            searchResultLimit: 100,
            noResultsText: 'Aucun résultat',
            noChoicesText: 'Aucun choix disponible'
        });
    }

    /**
     * Setup mobile sidebar toggle
     */
    setupMobileToggle() {
        if (this.elements.sidebarToggle && this.elements.sidebar) {
            this.elements.sidebarToggle.addEventListener('click', () => {
                this.elements.sidebar.classList.toggle('expanded');
            });
        }
    }

    /**
     * Initialize the MapLibre GL JS map with PMTiles
     */
    initMap() {
        // Register PMTiles protocol
        const protocol = new pmtiles.Protocol();
        maplibregl.addProtocol('pmtiles', protocol.tile);

        // Create layer switcher
        // 5th parameter is 'enabled' - true means visible by default
        this.layerSwitcher = new LayerSwitcher([
            new LayerGroup('Fond de carte', [
                new Layer('o', 'OpenStreetMap', 'base-osm', 'basemap', true),
                new Layer('s', 'Satellite', 'base-satellite', 'basemap'),
                new Layer('t', 'Topographique', 'base-topo', 'basemap'),
                new Layer('l', 'Clair', 'base-light', 'basemap'),
                new Layer('d', 'Sombre', 'base-dark', 'basemap')
            ]),
            new LayerGroup('Données', [
                new Layer('R', 'Départementales', 'roads-', 'data', true),
            ])
        ]);

        const style = {
            version: 8,
            sources: {
                'osm': {
                    type: 'raster',
                    tiles: [
                        'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
                        'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
                        'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png'
                    ],
                    tileSize: 256,
                    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                },
                'satellite': {
                    type: 'raster',
                    tiles: [
                        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
                    ],
                    tileSize: 256,
                    attribution: '&copy; <a href="https://www.esri.com/">Esri</a>, Maxar, Earthstar Geographics'
                },
                'topo': {
                    type: 'raster',
                    tiles: [
                        'https://a.tile.opentopomap.org/{z}/{x}/{y}.png',
                        'https://b.tile.opentopomap.org/{z}/{x}/{y}.png',
                        'https://c.tile.opentopomap.org/{z}/{x}/{y}.png'
                    ],
                    tileSize: 256,
                    attribution: '&copy; <a href="https://opentopomap.org">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>)'
                },
                'light': {
                    type: 'raster',
                    tiles: [
                        'https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
                        'https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
                        'https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'
                    ],
                    tileSize: 256,
                    attribution: '&copy; <a href="https://carto.com/">CARTO</a>'
                },
                'dark': {
                    type: 'raster',
                    tiles: [
                        'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
                        'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
                        'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'
                    ],
                    tileSize: 256,
                    attribution: '&copy; <a href="https://carto.com/">CARTO</a>'
                },
                'roads': {
                    type: 'vector',
                    url: 'pmtiles://data/roads.pmtiles'
                },
            },
            layers: [
                {
                    id: 'base-osm',
                    type: 'raster',
                    source: 'osm',
                    minzoom: 0,
                    maxzoom: 19
                },
                {
                    id: 'base-satellite',
                    type: 'raster',
                    source: 'satellite',
                    minzoom: 0,
                    maxzoom: 19
                },
                {
                    id: 'base-topo',
                    type: 'raster',
                    source: 'topo',
                    minzoom: 0,
                    maxzoom: 19
                },
                {
                    id: 'base-light',
                    type: 'raster',
                    source: 'light',
                    minzoom: 0,
                    maxzoom: 19
                },
                {
                    id: 'base-dark',
                    type: 'raster',
                    source: 'dark',
                    minzoom: 0,
                    maxzoom: 19
                },
                {
                    id: 'roads-hitarea',
                    type: 'line',
                    source: 'roads',
                    'source-layer': 'roads',
                    filter: ['all'],
                    paint: {
                        'line-color': 'transparent',
                        'line-width': 12,
                        'line-opacity': 0
                    }
                },
                {
                    id: 'roads-default',
                    type: 'line',
                    source: 'roads',
                    'source-layer': 'roads',
                    filter: ['all'],
                    paint: {
                        'line-color': this.lengthColorRamp,
                        'line-width': 3,
                        'line-opacity': 0.8
                    }
                },
                {
                    id: 'roads-selected',
                    type: 'line',
                    source: 'roads',
                    'source-layer': 'roads',
                    filter: ['==', 'ref', ''],
                    paint: {
                        'line-color': this.colors.selected,
                        'line-width': 5,
                        'line-opacity': 1
                    }
                }
            ]
        };

        // Set initial visibility for layer switcher
        this.layerSwitcher.setInitialVisibility(style);

        this.map = new maplibregl.Map({
            container: 'map',
            style: style,
            center: this.centerCoords,
            zoom: this.initialZoom
        });

        this.map.addControl(new maplibregl.NavigationControl());
        this.map.addControl(this.layerSwitcher, 'top-right');

        this.map.on('load', () => {
            this.showLoading(false);
            this.setupMapInteractions();
        });
    }

    /**
     * Setup map click and hover interactions
     */
    setupMapInteractions() {
        // Click on roads (use hitarea for easier clicking)
        this.map.on('click', 'roads-hitarea', (e) => {
            if (e.features && e.features.length > 0) {
                const props = e.features[0].properties;
                const ref = props.ref;

                // Show popup
                new maplibregl.Popup()
                    .setLngLat(e.lngLat)
                    .setHTML(`
                        <div class="popup-title">${ref}</div>
                        <div class="popup-info">
                            Route départementale<br>
                            ${props.total_length_km ? props.total_length_km.toFixed(1) + ' km (total)' : ''}
                        </div>
                    `)
                    .addTo(this.map);

                // Select the road
                this.selectRoadFromClick(ref);
            }
        });

        // Cursor change on hover
        this.map.on('mouseenter', 'roads-hitarea', () => {
            this.map.getCanvas().style.cursor = 'pointer';
        });

        this.map.on('mouseleave', 'roads-hitarea', () => {
            this.map.getCanvas().style.cursor = '';
        });
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Département selector change
        this.elements.deptSelect.addEventListener('change', (e) => {
            this.selectedDept = e.target.value || null;
            this.populateRoadSelector();
            this.clearSelection();
        });

        // Road selector change
        this.elements.roadSelect.addEventListener('change', (e) => {
            const ref = e.target.value;
            if (ref) {
                this.selectRoad(ref);
            } else {
                this.clearSelection();
            }
        });

        // Clear selection button
        if (this.elements.clearBtn) {
            this.elements.clearBtn.addEventListener('click', () => {
                this.clearSelection();
                // Reset road dropdown to placeholder
                this.roadChoices.setChoiceByValue('');
            });
        }
    }

    /**
     * Load the roads index
     */
    async loadRoadsIndex() {
        this.showLoading(true);
        try {
            const response = await fetch('data/index.json');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            this.roadsIndex = await response.json();
            this.populateDeptSelector();
            this.populateRoadSelector();
        } catch (error) {
            console.warn('Could not load index.json:', error);
            this.roadsIndex = { roads: [] };
            this.showError('Aucune donnée disponible. Exécutez le script d\'extraction.');
        }
    }

    /**
     * Populate the département selector dropdown
     */
    populateDeptSelector() {
        if (!this.roadsIndex || !this.roadsIndex.departements) {
            return;
        }

        // Sort départements by code
        const depts = Object.entries(this.roadsIndex.departements)
            .sort((a, b) => {
                // Handle alphanumeric sorting (2A, 2B at the end)
                const aNum = parseInt(a[0]) || 999;
                const bNum = parseInt(b[0]) || 999;
                if (aNum !== bNum) return aNum - bNum;
                return a[0].localeCompare(b[0]);
            });

        const choices = depts.map(([code, name]) => ({
            value: code,
            label: `${code} - ${name}`
        }));

        // Update Choices.js
        this.deptChoices.clearStore();
        this.deptChoices.setChoices([
            { value: '', label: 'Tous les départements', selected: true },
            ...choices
        ], 'value', 'label', true);
    }

    /**
     * Populate the road selector dropdown
     */
    populateRoadSelector() {
        if (!this.roadsIndex || !this.roadsIndex.roads) {
            return;
        }

        let mainRoads = this.roadsIndex.roads;

        // Filter by selected département if any
        if (this.selectedDept) {
            mainRoads = mainRoads.filter(road => road.ref.startsWith(this.selectedDept + '-'));
        }

        // Sort roads by descending length
        let sortedRoads = [...mainRoads].sort((a, b) => {
            return (b.total_length_km || 0) - (a.total_length_km || 0);
        });

        // When no département selected, limit to top 50 longest roads
        if (!this.selectedDept) {
            sortedRoads = sortedRoads.slice(0, 50);
        }

        // Build choices for Choices.js
        const choices = sortedRoads.map(road => {
            // Show D17 (123.45 km) - remove département prefix for display
            const lengthStr = road.total_length_km ? ` (${road.total_length_km.toFixed(1)} km)` : '';
            const displayName = road.ref.replace(/^\d+-/, '').replace(/^2[AB]-/, '');
            return {
                value: road.ref,
                label: displayName + lengthStr
            };
        });

        // Update Choices.js
        this.roadChoices.clearStore();

        // Add placeholder option with context message
        const placeholderLabel = this.selectedDept
            ? 'Toutes les routes'
            : 'Top 50 routes (sélectionnez un département pour voir toutes)';

        this.roadChoices.setChoices([
            { value: '', label: placeholderLabel, selected: true },
            ...choices
        ], 'value', 'label', true);
    }

    /**
     * Select a road from the dropdown
     */
    async selectRoad(ref) {
        if (this.isLoading) return;

        // Set selected road
        this.selectedRoad = ref;

        // Update road dropdown if not already set
        if (this.elements.roadSelect.value !== ref) {
            this.elements.roadSelect.value = ref;
        }

        // Highlight the road using filter
        this.highlightRoad(ref);

        // Show statistics
        this.showStatistics(ref);

        // Show clear button
        if (this.elements.clearBtn) {
            this.elements.clearBtn.classList.remove('hidden');
        }
    }

    /**
     * Select a road from map click
     */
    selectRoadFromClick(ref) {
        // Check if this is a main road
        const roadInfo = this.roadsIndex.roads.find(r => r.ref === ref);
        if (roadInfo) {
            this.selectRoad(ref);
            return;
        }

        console.warn('Road not found:', ref);
    }

    /**
     * Highlight a road using layer filters
     */
    highlightRoad(ref) {
        const roadInfo = this.roadsIndex.roads.find(r => r.ref === ref);
        if (!roadInfo) return;

        // Build filter for selected road
        this.map.setFilter('roads-selected', ['==', 'ref', ref]);

        // Reduce opacity of other roads
        this.map.setPaintProperty('roads-default', 'line-opacity', 0.3);

        // Query features to get bounds for zooming
        this.zoomToRoad(ref, roadInfo);
    }

    /**
     * Zoom to a road's extent with smart behavior:
     * - Road inside view bounds → do nothing
     * - Road intersects view bounds → extend view to include road
     * - Road outside view bounds → fit view to road bounds
     */
    zoomToRoad(ref, roadInfo) {
        // Use pre-computed bounds from index.json
        if (!roadInfo || !roadInfo.bounds) {
            return;
        }

        const [minLon, minLat, maxLon, maxLat] = roadInfo.bounds;
        const roadBounds = new maplibregl.LngLatBounds(
            [minLon, minLat],
            [maxLon, maxLat]
        );

        this.map.fitBounds(roadBounds, { padding: 100 });
    }

    /**
     * Clear road selection
     */
    clearSelection() {
        this.selectedRoad = null;
        this.elements.roadSelect.value = '';

        // Reset filters and opacity (only if map is loaded)
        if (this.map && this.map.isStyleLoaded()) {
            this.map.setFilter('roads-selected', ['==', 'ref', '']);
            this.map.setPaintProperty('roads-default', 'line-opacity', 0.8);
        }

        // Hide statistics
        this.hideStatistics();

        // Hide clear button
        if (this.elements.clearBtn) {
            this.elements.clearBtn.classList.add('hidden');
        }
    }

    /**
     * Show statistics for a road
     */
    showStatistics(ref) {
        const roadInfo = this.roadsIndex.roads.find(r => r.ref === ref);
        if (!roadInfo) return;

        // Update statistics
        this.elements.statRef.textContent = roadInfo.ref;
        this.elements.statLength.textContent = roadInfo.total_length_km
            ? roadInfo.total_length_km.toFixed(2) + ' km'
            : '-';

        // Show panel
        this.elements.statsPanel.classList.remove('hidden');
    }

    /**
     * Hide statistics panel
     */
    hideStatistics() {
        this.elements.statsPanel.classList.add('hidden');
    }

    /**
     * Show/hide loading indicator
     */
    showLoading(show) {
        this.isLoading = show;
        if (show) {
            this.elements.loading.classList.remove('hidden');
        } else {
            this.elements.loading.classList.add('hidden');
        }
    }

    /**
     * Show error message
     */
    showError(message) {
        this.elements.errorMessage.textContent = message;
        this.elements.errorMessage.classList.remove('hidden');

        // Auto-hide after 5 seconds
        setTimeout(() => {
            this.elements.errorMessage.classList.add('hidden');
        }, 5000);
    }
}

// Initialize the application when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new RoadsMapApp();
});
