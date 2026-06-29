/**
 * 户外徒步助手 v2.2 — Alpine.js 主应用
 * 优化: 独立加载状态、防重复提交、Markdown重写、异步等待修复
 */

// ====== Markdown 渲染器（逐行解析版） ======
function renderMarkdown(text) {
  if (!text) return '';
  const lines = text.split('\n');
  let html = '';
  let inList = false, listTag = '';
  let inTable = false;
  let tableHtml = '';
  let paraBuf = [];

  function flushPara() {
    if (paraBuf.length > 0) {
      html += '<p class="md-p">' + paraBuf.join('<br>') + '</p>';
      paraBuf = [];
    }
  }

  function closeList() {
    if (inList) { html += '</' + listTag + '>'; inList = false; listTag = ''; }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Table row
    if (/^\|.+\|$/.test(trimmed)) {
      flushPara(); closeList();
      if (!inTable) { inTable = true; tableHtml = '<table class="md-table">'; }
      const cells = trimmed.split('|').filter(c => c.trim());
      const nextLine = lines[i + 1]?.trim() || '';
      const isSep = /^\|[-| :]+\|$/.test(nextLine);
      const tag = isSep ? 'th' : 'td';
      tableHtml += '<tr>' + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>';
      if (isSep) { tableHtml += '<thead><tr>' + cells.map(c => `<th>${c.trim()}</th>`).join('') + '</tr></thead><tbody>'; i++; }
      const afterNext = lines[i + 1]?.trim() || '';
      if (!/^\|.+\|$/.test(afterNext)) {
        if (tableHtml.includes('<tbody>')) tableHtml += '</tbody>';
        tableHtml += '</table>';
        html += tableHtml;
        inTable = false;
        tableHtml = '';
      }
      continue;
    }

    // Headings
    if (/^### (.+)$/.test(line)) { flushPara(); closeList(); html += line.replace(/^### (.+)$/, '<h4 class="md-h4">$1</h4>'); continue; }
    if (/^## (.+)$/.test(line))  { flushPara(); closeList(); html += line.replace(/^## (.+)$/, '<h3 class="md-h3">$1</h3>'); continue; }
    if (/^# (.+)$/.test(line))   { flushPara(); closeList(); html += line.replace(/^# (.+)$/, '<h2 class="md-h2">$1</h2>'); continue; }

    // Horizontal rule
    if (/^---$/.test(trimmed)) { flushPara(); closeList(); html += '<hr class="md-hr">'; continue; }

    // Unordered list
    if (/^- (.+)$/.test(line)) {
      flushPara();
      if (!inList || listTag !== 'ul') { closeList(); html += '<ul class="md-ul">'; inList = true; listTag = 'ul'; }
      html += '<li>' + line.replace(/^- (.+)$/, '$1') + '</li>';
      continue;
    }
    // Ordered list
    if (/^\d+\. (.+)$/.test(line)) {
      flushPara();
      if (!inList || listTag !== 'ol') { closeList(); html += '<ol class="md-ol">'; inList = true; listTag = 'ol'; }
      html += '<li>' + line.replace(/^\d+\. (.+)$/, '$1') + '</li>';
      continue;
    }

    // Close list on non-list line
    closeList();

    // Empty line = paragraph break
    if (trimmed === '') { flushPara(); continue; }

    // Regular text
    paraBuf.push(line);
  }

  flushPara();
  closeList();

  // Inline formatting (applied after block structure to avoid nesting issues)
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/`([^`]+)`/g, '<code class="md-code">$1</code>');

  return html;
}

// ====== History Manager ======
const HISTORY_KEY = 'outdoor_buddy_history';
const MAX_HISTORY = 50;

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
  catch { return []; }
}
function saveHistory(entry) {
  let h = loadHistory();
  h.unshift({ ...entry, time: new Date().toISOString() });
  if (h.length > MAX_HISTORY) h = h.slice(0, MAX_HISTORY);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(h));
}
function clearHistory() { localStorage.removeItem(HISTORY_KEY); }

// ====== Scroll helper ======
function scrollTo(sel) {
  const el = document.getElementById(sel);
  if (el) el.scrollTop = el.scrollHeight;
}

// ====== Alpine App ======
document.addEventListener('alpine:init', () => {
  Alpine.data('app', () => ({
    // === State ===
    page: 'home',
    user: null,
    // Per-page loading states (Phase 1.1)
    loading: {
      route: false,
      equipment: false,
      ticket: false,
      weather: false,
      plan: false,
      forum: false,
      qa: false,
    },
    // Double-click guard (Phase 2.1)
    inFlight: {
      searchRoute: false, recommendEquip: false, queryTicket: false,
      queryWeather: false, planQueryWeather: false, planGenerate: false, sendQA: false, planQueryTicket: false,
      doLogin: false, doRegister: false, forumCreate: false,
      forumQuickReply: false, forumSubmitReply: false,
      addFavorite: false, deleteFav: false,
    },
    toastMsg: '',
    _toastTimer: null,  // Phase 1.4: track timeout for race fix
    history: loadHistory(),
    // Auth
    authMode: 'login',
    loginUsername: '', loginPassword: '',
    regUsername: '', regEmail: '', regPassword: '',
    showAuth: false,
    // Password reset
    showForgotPassword: false, forgotEmail: '', forgotStep: 1, resetToken: '', resetNewPassword: '',
    // Route
    routeKeyword: '',
    routeResults: null,
    // Equipment
    equipKeyword: '', equipMode: 'light', equipDays: 3, equipSeason: '夏', equipResults: null,
    // Ticket
    ticketFrom: '', ticketTo: '', ticketDate: new Date().toISOString().split('T')[0], ticketResults: null,
    // Weather
    weatherLocation: '', weatherResults: null,
    // Plan
    planSearchKw: '', planSearchResults: null, planSelectedRouteIdx: -1, planSelectedRoute: null,
    planDate: new Date().toISOString().split('T')[0], planDays: 3, planEquipMode: 'light',
    planWeatherData: null, planWeatherQuerying: false, planTicketFrom: '', planTicketTo: '', planTicketData: null, planTicketQuerying: false,
    planDifficulty: '中等', planTerrain: '山地', planAltitude: 2000, planClimb: 1500, planResults: null,
    // Plan view modal
    planViewOpen: false, planViewTitle: '', planViewContent: '',
    // QA
    qaMessages: [], qaInput: '',
    // Favorites
    favorites: [], favRoutes: [], favPlans: [],
    // Route drawer
    routeDrawerOpen: false, routeDrawerData: null,
    // Forum
    forumView: 'list',
    forumLightboxOpen: false, forumLightboxSrc: '',
    forumExpandedPosts: {},
    forumReplyInputFor: null,
    forumExpandedReplies: {},
    forumLoadingReplies: {},
    forumCatId: null,
    forumCategories: [], forumPosts: [], forumTotal: 0, forumPage: 1,
    forumLoading: false,
    forumDetailLoading: false,
    forumPostDetail: null,
    forumNewPost: { catId: null, title: '', content: '', images: [] },
    forumReplyContent: '',
    forumReplyImages: [],

    // Avatar
    avatarUploading: false, avatarMsg: '', avatarPassed: true,

    // === Init ===
    async init() {
      if (isLoggedIn()) await this.loadUser();
      this.history = loadHistory();
      // Check URL for reset token
      const params = new URLSearchParams(window.location.search);
      const token = params.get('token');
      if (token) {
        this.resetToken = token;
        this.forgotStep = 2;
        this.showForgotPassword = true;
        // Clean URL
        window.history.replaceState({}, '', window.location.pathname);
      }
    },

    // === Navigation (preserves state, per-page loading) ===
    async navigate(p) {
      if (this.page !== p) {
        this.page = p;
      }
      if (p === 'profile') { await this.loadFavorites(); this.history = loadHistory(); }  // Phase 4.3
      if (p === 'forum') {
        this.forumView = 'list';
        this.forumPage = 1;
        this.forumLoadCategories();
        this.forumLoadPosts();
      }
    },

    // === Helpers ===
    md(text) { return renderMarkdown(text); },

    // === Plan Step Progress ===
    get planActiveStep() {
      if (!this.planSelectedRoute) return 0;
      if (!this.planWeatherData) return 1;
      if (!this.planTicketData && this.planTicketFrom && this.planTicketTo) return 2;
      if (this.planWeatherData && (this.planTicketData || !this.planTicketFrom)) return 3;
      return 4;
    },

    // === Toast (Phase 1.4: race condition fix) ===
    toast(msg) {
      if (this._toastTimer) clearTimeout(this._toastTimer);
      this.toastMsg = msg;
      this._toastTimer = setTimeout(() => {
        if (this.toastMsg === msg) this.toastMsg = '';
      }, 2500);
    },

    // === Auth ===
    toggleAuth() { this.showAuth = !this.showAuth; },
    async doLogin() {
      if (this.inFlight.doLogin) return;
      this.inFlight.doLogin = true;
      try {
        const res = await API.auth.login(this.loginUsername, this.loginPassword);
        setToken(res.data.access_token);
        this.user = res.data.user;
        this.showAuth = false;
        this.toast('登录成功');
        this.navigate('home');
      } catch (e) { this.toast(e.message); }
      finally { this.inFlight.doLogin = false; }
    },
    async doRegister() {
      if (this.inFlight.doRegister) return;
      if (this.regPassword.length < 6) return this.toast('密码至少6位');
      if (!this.regEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.regEmail)) return this.toast('请输入有效的邮箱地址');
      this.inFlight.doRegister = true;
      try {
        await API.auth.register(this.regUsername, this.regEmail, this.regPassword);
        this.toast('注册成功，请登录');
        this.authMode = 'login';
        this.loginUsername = this.regUsername;
        this.regUsername = ''; this.regEmail = ''; this.regPassword = '';
      } catch (e) { this.toast(e.message); }
      finally { this.inFlight.doRegister = false; }
    },
    async loadUser() {
      try {
        const r = await API.auth.me();
        this.user = r.data;
      } catch (e) {
        // Phase 4.1: Only clear token on 401, not on network errors
        if (e.status === 401) clearToken();
        else console.warn('加载用户信息失败:', e.message);
      }
    },
    logout() { clearToken(); this.user = null; this.toast('已退出'); this.navigate('home'); },
    // === Password Reset ===
    async forgotPassword() {
      if (!this.forgotEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.forgotEmail)) return this.toast('请输入有效的邮箱地址');
      try {
        const r = await API.auth.forgotPassword(this.forgotEmail);
        if (r.data?.reset_token) {
          this.resetToken = r.data.reset_token;
          this.toast('重置令牌已生成，请设置新密码');
          this.forgotStep = 2;
        } else {
          this.toast(r.message || '重置链接已发送');
          this.showForgotPassword = false;
        }
      } catch (e) { this.toast(e.message); }
    },
    async resetPassword() {
      if (this.resetNewPassword.length < 6) return this.toast('新密码至少6位');
      try {
        await API.auth.resetPassword(this.resetToken, this.resetNewPassword);
        this.toast('密码重置成功，请登录');
        this.showForgotPassword = false;
        this.forgotStep = 1;
        this.forgotEmail = '';
        this.resetToken = '';
        this.resetNewPassword = '';
        this.authMode = 'login';
        this.showAuth = true;
      } catch (e) { this.toast(e.message); }
    },

    // === Avatar ===
    async avatarUpload(e) {
      const file = e.target.files[0];
      if (!file) return;
      this.avatarUploading = true;
      this.avatarMsg = '';
      try {
        const res = await API.auth.uploadAvatar(file);
        if (res.data?.passed) {
          this.avatarMsg = '✅ ' + res.data.reason;
          this.avatarPassed = true;
          this.user.avatar_url = res.data.avatar_url;
          this.toast('头像已更新');
        } else {
          this.avatarMsg = '❌ ' + (res.data?.reason || res.message || '审核未通过');
          this.avatarPassed = false;
        }
      } catch (e) {
        this.avatarMsg = '❌ ' + (e.message || '上传失败');
        this.avatarPassed = false;
      }
      this.avatarUploading = false;
    },
    avatarDrop(e) {
      const file = e.dataTransfer.files[0];
      if (!file) return;
      const input = document.getElementById('avatarInput');
      const dt = new DataTransfer(); dt.items.add(file);
      input.files = dt.files;
      input.dispatchEvent(new Event('change'));
    },

    // === Route Search (Phase 1.1: per-page loading, Phase 2.1: guard) ===
    async searchRoute(keyword) {
      if (this.inFlight.searchRoute) return;
      const kw = keyword || this.routeKeyword;
      if (!kw) return this.toast('请输入关键词');
      this.inFlight.searchRoute = true;
      this.loading.route = true;
      try {
        const res = await API.route.search(kw);
        this.routeResults = res.data;
        this.routeKeyword = kw;
        saveHistory({ type: 'route', title: kw, summary: `找到 ${res.data.routes?.length || 0} 条路线` });
        this.history = loadHistory();
      } catch (e) { this.toast(e.message); }
      finally { this.loading.route = false; this.inFlight.searchRoute = false; }
    },
    async restoreRoute(item) {
      this.routeKeyword = item.title;
      this.navigate('route');      // Phase 4.4: navigate first, then search
      await this.searchRoute(item.title);
    },
    openRouteDrawer(route) {
      this.routeDrawerData = route;
      this.routeDrawerOpen = true;
    },
    openFavoriteRoute(f) {
      const content = f.content;
      if (content && content.name) {
        this.routeDrawerData = content;
        this.routeDrawerOpen = true;
      } else {
        this.routeKeyword = f.title;
        this.restoreRoute({ title: f.title });
      }
    },

    // === Equipment ===
    async searchEquip(kw) {
      const keyword = kw || this.equipKeyword;
      if (!keyword) return this.toast('请输入装备关键词');
      this.loading.equipment = true;
      try {
        const res = await API.equipment.search(keyword, null);
        this.equipResults = res.data;
        saveHistory({ type: 'equipment', title: keyword, summary: '装备查询' });
        this.history = loadHistory();
      } catch (e) { this.toast(e.message); }
      finally { this.loading.equipment = false; }
    },
    async recommendEquip() {
      if (this.inFlight.recommendEquip) return;
      this.inFlight.recommendEquip = true;
      this.loading.equipment = true;
      try {
        const res = await API.equipment.recommend({
          mode: this.equipMode, days: this.equipDays,
          season: this.equipSeason, terrain: '山地', people_count: 1
        }, { timeout: 180000 });
        this.equipResults = res.data;
        saveHistory({ type: 'equipment', title: `${this.equipMode === 'heavy' ? '重装' : '轻装'}装备方案`, summary: `${this.equipDays}天 ${this.equipSeason}季` });
        this.history = loadHistory();
      } catch (e) { this.toast(e.message); }
      finally { this.loading.equipment = false; this.inFlight.recommendEquip = false; }
    },

    // === Ticket ===
    async queryTicket() {
      if (this.inFlight.queryTicket) return;
      if (!this.ticketFrom || !this.ticketTo) return this.toast('请填写出发和目的城市');
      this.inFlight.queryTicket = true;
      this.loading.ticket = true;
      try {
        const res = await API.ticket.query(this.ticketFrom, this.ticketTo, this.ticketDate);
        this.ticketResults = res.data;
        saveHistory({ type: 'ticket', title: `${this.ticketFrom} → ${this.ticketTo}`, summary: `${this.ticketDate} 找到 ${res.data.tickets?.length || 0} 个车次` });
        this.history = loadHistory();
      } catch (e) { this.toast(e.message); }
      finally { this.loading.ticket = false; this.inFlight.queryTicket = false; }
    },

    // === Weather ===
    async queryWeather(loc) {
      if (this.inFlight.queryWeather) return;
      const location = loc || this.weatherLocation;
      if (!location) return this.toast('请输入地点');
      this.inFlight.queryWeather = true;
      this.loading.weather = true;
      try {
        const res = await API.weather.query(location, null, 7);
        this.weatherResults = res.data;
        this.weatherLocation = location;
        saveHistory({ type: 'weather', title: location, summary: '7天天气预报' });
        this.history = loadHistory();
      } catch (e) { this.toast(e.message); }
      finally { this.loading.weather = false; this.inFlight.queryWeather = false; }
    },

    // === Plan ===
    async planSearchRoute() {
      if (!this.planSearchKw) return this.toast('请输入关键词');
      this.loading.plan = true;
      try {
        const res = await API.route.search(this.planSearchKw);
        this.planSearchResults = res.data?.routes || [];
        this.planSelectedRouteIdx = -1;
        this.planSelectedRoute = null;
        if (!this.planSearchResults.length) this.toast('未找到路线');
	        else this.toast('找到 ' + this.planSearchResults.length + ' 条路线，请点击选择');
      } catch (e) { this.toast(e.message); }
      finally { this.loading.plan = false; }
    },
    planSelectRoute(i) {
      console.log('planSelectRoute called, i=' + i);
      if (i < 0 || !this.planSearchResults?.[i]) return;
      this.planSelectedRouteIdx = i;
      this.planSelectedRoute = this.planSearchResults[i];
      console.log('planSelectedRoute set to:', this.planSelectedRoute?.name);
      const r = this.planSelectedRoute;
      // Phase 4.5: wrap in String() to handle numeric API fields
      const elevStr = String(r.elevation_gain ?? '');
      const altStr = String(r.max_altitude ?? '');
      const durStr = String(r.duration ?? '');
      const elevMatch = elevStr.match(/(\d+)/);
      const altMatch = altStr.match(/(\d+)/);
      const durMatch = durStr.match(/(\d+)/);
      if (altMatch) this.planAltitude = parseInt(altMatch[0]);
      if (elevMatch) this.planClimb = parseInt(elevMatch[0]);
      if (durMatch && parseInt(durMatch[0]) >= 1) this.planDays = parseInt(durMatch[0]);
      if (r.difficulty) this.planDifficulty = r.difficulty;
      this.planTerrain = '山地';
      const cityMap = {
        '武功山': '萍乡', '雨崩': '香格里拉', '虎跳峡': '丽江',
        '四姑娘山': '成都', '黄山': '黄山', '泰山': '泰安',
        '华山': '西安', '峨眉山': '成都', '太白山': '宝鸡',
        '五台山': '忻州', '稻城': '成都', '贡嘎': '康定',
        '梅里': '德钦', '长白山': '延吉', '庐山': '九江',
        '张家界': '张家界', '三清山': '上饶', '雁荡山': '温州',
        '太行': '新乡', '秦岭': '西安', '大别山': '六安',
        '武夷山': '武夷山', '普陀山': '舟山', '九华山': '池州',
      };
      for (const [key, city] of Object.entries(cityMap)) {
        if (r.name?.includes(key) || this.planSearchKw?.includes(key)) {
          this.planTicketTo = city;
          break;
        }
      }
      this.toast('已选择: ' + r.name + (this.planTicketTo ? ' | 目的地: ' + this.planTicketTo : ''));
    },
    async planQueryWeather() {
      if (!this.planSelectedRoute) return;
      if (this.planWeatherQuerying) return;
      this.planWeatherQuerying = true;
      try {
        const res = await API.weather.query(this.planSearchKw, this.planDate, 7);
        this.planWeatherData = res.data;
      } catch (e) { this.toast(e.message); }
      finally { this.planWeatherQuerying = false; }
    },
    async planQueryTicket() {
      if (!this.planTicketFrom || !this.planTicketTo) return;
      this.planTicketQuerying = true;
      try {
        const res = await API.ticket.query(this.planTicketFrom, this.planTicketTo, this.planDate);
        this.planTicketData = res.data;
        this.toast(`找到 ${res.data.tickets?.length || 0} 个车次`);
      } catch (e) { this.toast(e.message); }
      finally { this.planTicketQuerying = false; }
    },
    async planGenerateAll() {
      if (this.inFlight.planGenerate) return;
      this.inFlight.planGenerate = true;
      this.loading.plan = true;
      try {
        // Auto-fetch weather + tickets in parallel
        const fetchers = [];
        if (!this.planWeatherData && this.planSelectedRoute) {
          this.planWeatherQuerying = true;
          fetchers.push((async () => {
            try { const r = await API.weather.query(this.planSearchKw, this.planDate, 7); this.planWeatherData = r.data; }
            catch (e) { /* silent */ }
            finally { this.planWeatherQuerying = false; }
          })());
        }
        if (this.planTicketFrom && this.planTicketTo && !this.planTicketData) {
          this.planTicketQuerying = true;
          fetchers.push((async () => {
            try { const r = await API.ticket.query(this.planTicketFrom, this.planTicketTo, this.planDate); this.planTicketData = r.data; }
            catch (e) { /* silent */ }
            finally { this.planTicketQuerying = false; }
          })());
        }
        if (fetchers.length) await Promise.all(fetchers);
        const res = await API.plan.generate({
          days: this.planDays, max_altitude: this.planAltitude,
          elevation_gain: this.planClimb, difficulty: this.planDifficulty,
          terrain: this.planTerrain, mode: this.planEquipMode,
          route_name: this.planSelectedRoute?.name || '',
          location: this.planSearchKw,
        }, this.planWeatherData || null, null, this.planTicketData || null, { timeout: 180000 });
        this.planResults = res.data;
        saveHistory({ type: 'plan', title: `${this.planDays}天 ${this.planSearchKw}行程预案`, summary: `难度: ${this.planDifficulty}` });
        this.history = loadHistory();
        this.toast('预案生成成功');
      } catch (e) { this.toast(e.message); }
      finally { this.loading.plan = false; this.inFlight.planGenerate = false; }
    },

    // === QA ===
    async sendQA() {
      if (this.inFlight.sendQA) return;
      const msg = this.qaInput.trim();
      if (!msg) return;
      this.inFlight.sendQA = true;
      this.loading.qa = true;
      this.qaMessages.push({ role: 'user', content: msg });
      this.qaInput = '';
      const loadingIdx = this.qaMessages.length;
      this.qaMessages.push({ role: 'assistant', content: '...', loading: true });
      this.$nextTick(() => scrollTo('qa-scroll'));
      try {
        const res = await API.qa.chat(msg);
        const answer = res.data?.answer || '无响应';
        this.qaMessages[loadingIdx] = { role: 'assistant', content: answer, html: renderMarkdown(answer) };
        saveHistory({ type: 'qa', title: msg.slice(0, 40), summary: answer.slice(0, 80) });
        this.history = loadHistory();
      } catch (e) {
        this.qaMessages[loadingIdx] = { role: 'assistant', content: '服务暂不可用: ' + e.message };
      }
      this.loading.qa = false;
      this.inFlight.sendQA = false;
      this.$nextTick(() => scrollTo('qa-scroll'));
    },

    // === Favorites ===
    async loadFavorites() {
      if (!isLoggedIn()) return;
      try {
        const res = await API.favorite.list(null);
        const all = res.data?.favorites || [];
        this.favorites = all;
        this.favRoutes = all.filter(f => f.fav_type === 'route');
        this.favPlans = all.filter(f => f.fav_type === 'plan');
      } catch (e) { console.warn('加载收藏失败:', e.message); }  // Phase 4.9
    },
    async addFavorite(type, title, content) {
      if (!isLoggedIn()) return this.toast('请先登录');
      if (this.inFlight.addFavorite) return;
      this.inFlight.addFavorite = true;
      try { await API.favorite.add(type, title, content || {}); this.toast('已收藏'); }
      catch (e) { this.toast(e.message); }
      finally { this.inFlight.addFavorite = false; }
    },
    async deleteFav(id) {
      if (this.inFlight.deleteFav) return;
      this.inFlight.deleteFav = true;
      try { await API.favorite.delete(id); this.toast('已删除'); await this.loadFavorites(); }
      catch (e) { this.toast(e.message); }
      finally { this.inFlight.deleteFav = false; }
    },
    async exportContent(type, content) {
      try {
        const res = await API.favorite.export(type, content || {});
        if (res.data?.text) { await navigator.clipboard.writeText(res.data.text); this.toast('已复制到剪贴板'); }
        else this.toast('导出内容为空');
      } catch (e) { this.toast('导出失败'); }
    },

    // === History ===
    clearAllHistory() { clearHistory(); this.history = []; this.toast('历史已清除'); },
    historyIcon(t) { return t === 'route' ? '◎' : t === 'equipment' ? '⬡' : t === 'ticket' ? '≡' : t === 'weather' ? '◐' : t === 'plan' ? '▦' : '◈'; },
    historyLabel(t) { return t === 'route' ? '路线' : t === 'equipment' ? '装备' : t === 'ticket' ? '票务' : t === 'weather' ? '天气' : t === 'plan' ? '预案' : '问答'; },
    formatTime(t) { if (!t) return ''; const d = new Date(t); return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; },

    // === Plan View / Download ===
    viewPlan(f) {
      if (!f || !f.title) return;  // Phase 4.6: null guard
      this.planViewTitle = f.title;
      const c = f.content || {};
      this.planViewContent = [
        c.altitude_plan, c.fitness_plan, c.weather_risk_plan,
        c.environment_knowledge, c.daily_guide
      ].filter(Boolean).join('\n\n---\n\n');
      this.planViewOpen = true;
    },
    downloadPlan() {
      if (!this.planResults) return;
      this._doDownload(this.planSearchKw || '行程预案', this.planResults);
    },
    downloadEquipPoster() {
      if (!this.equipResults) return;
      const title = `${this.equipMode === 'heavy' ? '重装' : '轻装'}徒步装备方案`;
      this._doDownload(title, this.equipResults);
    },
    downloadPlanPoster(f) {
      if (!f || !f.title) return this.toast('数据不完整，无法下载');  // Phase 4.6
      this._doDownload(f.title, f.content || {});
    },
    _doDownload(title, content) {
      let sections = [];
      if (content.equipment_list) {
        sections = [
          { emoji: '🎒', title: '装备清单', text: content.equipment_list },
          { emoji: '📋', title: '模式说明', text: (content.mode === 'heavy' ? '重装徒步（全程背负）' : '轻装徒步（有补给住宿）') + (content.recommendation ? '\n\n' + content.recommendation : '') },
        ].filter(s => s.text);
      } else {
        sections = [
          { emoji: '🏔️', title: '海拔健康应对', text: content.altitude_plan },
          { emoji: '💪', title: '体能与行程分配', text: content.fitness_plan },
          { emoji: '⚠️', title: '天气风险应对', text: content.weather_risk_plan },
          { emoji: '🌲', title: '环境安全知识', text: content.environment_knowledge },
          { emoji: '📅', title: '每日行动指南', text: content.daily_guide },
        ].filter(s => s.text);
      }

      const html = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>${title}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Inter:wght@300;400;600&display=swap');
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:'Inter',sans-serif;background:#f5f0eb;color:#2c2420;line-height:1.8;max-width:800px;margin:0 auto;padding:40px 20px}
  .poster-header{background:linear-gradient(135deg,#1a3a2a,#0d1f16);color:#fff;padding:40px;border-radius:16px;margin-bottom:24px;text-align:center}
  .poster-header h1{font-family:'DM Serif Display',serif;font-size:2rem;margin-bottom:8px}
  .poster-header .subtitle{color:#8ba888;font-size:.9rem}
  .poster-section{background:#faf7f2;border-radius:12px;padding:24px;margin-bottom:16px;border-left:4px solid #c77d20}
  .poster-section h2{font-family:'DM Serif Display',serif;font-size:1.2rem;color:#1a3a2a;margin-bottom:12px}
  .poster-section .content{font-size:.9rem;white-space:pre-wrap;line-height:1.8}
  .poster-footer{text-align:center;margin-top:32px;padding:20px;color:#8ba888;font-size:.8rem;border-top:1px solid #e8ddd0}
  @media print{body{background:#fff}.poster-header{background:#1a3a2a!important;-webkit-print-color-adjust:exact}}
</style></head><body>
<div class="poster-header"><h1>${title}</h1><div class="subtitle">Outdoor Buddy · 户外徒步助手 · ${new Date().toLocaleDateString('zh-CN')}</div></div>
${sections.map(s => `<div class="poster-section"><h2>${s.emoji} ${s.title}</h2><div class="content">${s.text}</div></div>`).join('')}
<div class="poster-footer">Generated by Outdoor Buddy · LangGraph Powered</div>
</body></html>`;

      const blob = new Blob([html], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `${title}.html`; a.click();
      URL.revokeObjectURL(url);
      this.toast('海报已下载');
    },
    favTypeLabel(t) { return t === 'route' ? '路线' : t === 'equipment' ? '装备' : '预案'; },
    truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '...' : s || ''; },

    // === Forum ===
    async forumLoadCategories() {
      try { const r = await API.forum.categories(); this.forumCategories = r.data || []; }
      catch(e) { this.toast('加载分类失败'); }  // Phase 4.9
    },
    async forumLoadPosts() {
      this.loading.forum = true;
      try {
        const r = await API.forum.listPosts(this.forumCatId, this.forumPage);
        this.forumPosts = r.data?.posts || [];
        this.forumTotal = r.data?.total || 0;
      } catch(e) { this.toast('加载失败: ' + e.message); }
      finally { this.loading.forum = false; }
    },
    async forumViewPost(p) {
      this.forumView = 'detail';
      this.forumDetailLoading = true;
      try {
        const r = await API.forum.getPost(p.id);
        this.forumPostDetail = r.data;
      } catch(e) { this.toast(e.message); }
      finally { this.forumDetailLoading = false; }
    },
    async forumCreatePost() {
      if (this.inFlight.forumCreate) return;
      if (!this.forumNewPost.content) return this.toast('请输入内容');
      if (!this.forumNewPost.catId) {
        this.forumNewPost.catId = this.forumCategories[0]?.id;
        if (!this.forumNewPost.catId) return this.toast('请先选择分类');
      }
      this.inFlight.forumCreate = true;
      try {
        await API.forum.createPost({
          title: this.forumNewPost.title, content: this.forumNewPost.content,
          category_id: this.forumNewPost.catId, images: this.forumNewPost.images
        });
        this.toast('发帖成功');
        this.forumNewPost = { catId: null, title: '', content: '', images: [] };
        this.forumView = 'list';
        await this.forumLoadPosts();
      } catch(e) { this.toast(e.message); }
      finally { this.inFlight.forumCreate = false; }
    },
    async forumUploadImage(e) {
      const files = e.target.files;
      for (const file of files) {
        try {
          const r = await API.forum.uploadImage(file);
          if (r.data?.url) this.forumNewPost.images.push(r.data.url);
        } catch(ex) { this.toast('上传失败: ' + ex.message); }
      }
    },
    async forumReplyUploadImage(e) {
      const file = e.target.files[0];
      if (!file) return;
      try {
        const r = await API.forum.uploadImage(file);
        if (r.data?.url) this.forumReplyImages.push(r.data.url);
      } catch(ex) { this.toast('上传失败: ' + ex.message); }
    },
    async forumSubmitReply() {
      if (this.inFlight.forumSubmitReply) return;
      if (!this.forumReplyContent.trim()) return this.toast('请输入回复内容');
      this.inFlight.forumSubmitReply = true;
      try {
        await API.forum.createReply(this.forumPostDetail.id, {
          content: this.forumReplyContent, images: this.forumReplyImages
        });
        this.toast('回复成功');
        this.forumReplyContent = '';
        this.forumReplyImages = [];
        await this.forumViewPost(this.forumPostDetail);
      } catch(e) { this.toast(e.message); }
      finally { this.inFlight.forumSubmitReply = false; }
    },

    // === Forum Delete ===
    async forumDeletePost(id) {
      if (!confirm('确定删除这篇帖子吗？')) return;
      try { await API.forum.deletePost(id); this.toast('已删除'); this.forumView = 'list'; await this.forumLoadPosts(); }
      catch(e) { this.toast(e.message); }
    },
    async forumDeleteReply(replyId, postId) {
      if (!confirm('确定删除这条回复吗？')) return;
      try {
        await API.forum.deleteReply(replyId);
        this.toast('已删除');
        if (postId && this.forumExpandedReplies[postId]) {
          await this.forumLoadReplies(postId);
        }
        await this.forumLoadPosts();
      } catch(e) { this.toast(e.message); }
    },

    // === Image Lightbox (Phase 2.8: keyboard focus) ===
    forumOpenLightbox(src) {
      this.forumLightboxSrc = src;
      this.forumLightboxOpen = true;
      this.$nextTick(() => {
        const el = document.querySelector('.lightbox-overlay');
        if (el) el.focus();
      });
    },
    forumCloseLightbox() { this.forumLightboxOpen = false; this.forumLightboxSrc = ''; },

    // === Image Expand (Phase 1.2 compatible: uses reactive keys) ===
    forumToggleImages(postId) {
      this.forumExpandedPosts = { ...this.forumExpandedPosts, [postId]: !this.forumExpandedPosts[postId] };
    },
    forumVisibleImages(images, postId) {
      if (!images || !images.length) return [];
      return this.forumExpandedPosts[postId] ? images : images.slice(0, 3);
    },
    forumHasMoreImages(images) { return images && images.length > 3; },

    // === Inline Reply ===
    forumToggleReplyInput(postId) {
      this.forumReplyInputFor = this.forumReplyInputFor === postId ? null : postId;
      this.forumReplyContent = '';
    },
    async forumQuickReply(postId) {
      if (this.inFlight.forumQuickReply) return;
      const content = this.forumReplyContent?.trim();
      if (!content) return;
      this.inFlight.forumQuickReply = true;
      this.forumReplyContent = '';
      this.forumReplyInputFor = null;
      try {
        await API.forum.createReply(postId, { content, images: [] });
        this.toast('回复成功');
        if (this.forumExpandedReplies[postId]) {
          await this.forumLoadReplies(postId);
        }
        await this.forumLoadPosts();
      } catch(e) { this.toast(e.message); }
      finally { this.inFlight.forumQuickReply = false; }
    },

    async forumToggleReplies(postId) {
      if (this.forumExpandedReplies[postId]) {
        const newReplies = { ...this.forumExpandedReplies };
        delete newReplies[postId];
        this.forumExpandedReplies = newReplies;
      } else {
        await this.forumLoadReplies(postId);
      }
    },

    async forumLoadReplies(postId) {
      this.forumLoadingReplies = { ...this.forumLoadingReplies, [postId]: true };
      try {
        const r = await API.forum.getReplies(postId);
        this.forumExpandedReplies = { ...this.forumExpandedReplies, [postId]: r.data?.replies || [] };
      } catch(e) { this.toast(e.message); }
      finally {
        this.forumLoadingReplies = { ...this.forumLoadingReplies, [postId]: false };
      }
    },
  }));
});
