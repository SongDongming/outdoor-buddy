/**
 * API 客户端 — v2.1
 * 新增: 请求超时、AbortController、状态码、非JSON容错
 */
const API_BASE = '/api/v1';
let authToken = localStorage.getItem('token') || '';
const sessionId = localStorage.getItem('sessionId') || ('sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9));

if (!localStorage.getItem('sessionId')) localStorage.setItem('sessionId', sessionId);

function apiHeaders(){
  const h = {'Content-Type':'application/json','X-Session-Id':sessionId};
  if (authToken) h['Authorization'] = 'Bearer ' + authToken;
  return h;
}

async function api(method, path, body=null, options={}){
  const { timeout = 60000, retries = 0, signal: extSignal } = options;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  if (extSignal) extSignal.addEventListener('abort', () => controller.abort());

  const opts = { method, headers: apiHeaders(), signal: controller.signal };
  if (body) opts.body = JSON.stringify(body);

  let lastError;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(API_BASE + path, opts);
      clearTimeout(timeoutId);
      const text = await res.text();
      let data;
      try { data = JSON.parse(text); }
      catch { data = { detail: text || '服务器返回了无效数据' }; }
      if (!res.ok) {
        // 401：令牌失效/过期 → 全局清 token 并通知应用刷新登录态
        if (res.status === 401) {
          clearToken();
          window.dispatchEvent(new CustomEvent('app:unauthorized'));
        }
        const err = new Error(data.detail || data.message || '请求失败');
        err.status = res.status;
        throw err;
      }
      return data;
    } catch (e) {
      lastError = e;
      if (e.name === 'AbortError' && !extSignal?.aborted) {
        lastError = new Error('请求超时，请检查网络连接');
        lastError.status = 408;
        break; // don't retry timeout
      }
      if (attempt < retries && e.status !== 401 && e.status !== 403 && e.status !== 404) {
        await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
      } else if (attempt < retries) {
        break; // don't retry auth/permission errors
      }
    }
  }
  clearTimeout(timeoutId);
  throw lastError;
}

const API = {
  auth: {
    register: (u,e,p) => api('POST','/auth/register',{username:u,email:e,password:p}),
    login: (u,p) => api('POST','/auth/login',{username:u,password:p}),
    me: () => api('GET','/auth/me'),
    forgotPassword: (email) => api('POST','/auth/forgot-password',{email}),
    resetPassword: (token, password) => api('POST','/auth/reset-password',{token,new_password:password}),
    checkEmail: (email) => api('GET','/auth/check-email?email='+encodeURIComponent(email)),
    uploadAvatar: async (file) => {
      const fd = new FormData(); fd.append('file', file);
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);
      const opts = {method:'POST', headers:{}, body:fd, signal: controller.signal};
      if (authToken) opts.headers['Authorization'] = 'Bearer '+authToken;
      opts.headers['X-Session-Id'] = sessionId;
      let res, data;
      try {
        res = await fetch(API_BASE+'/auth/avatar', opts);
        data = await res.json();
      } catch(e) {
        clearTimeout(timeoutId);
        if (e.name === 'AbortError') throw new Error('上传超时');
        throw e;
      }
      clearTimeout(timeoutId);
      if (!res.ok) throw new Error(data.detail || data.message || '上传失败');
      return data;
    },
  },
  route: { search: (kw) => api('POST','/routes/search',{keyword:kw}) },
  equipment: {
    search: (kw,cat) => api('POST','/equipment/search',{keyword:kw,category:cat}),
    recommend: (p, opts) => api('POST','/equipment/recommend',p,opts),
    recommendStream: (p, onEvent) => streamEvent('/equipment/recommend', {...p, stream:true}, onEvent),
    categories: () => api('GET','/equipment/categories'),
  },
  ticket: { query: (f,t,d) => api('POST','/tickets/query',{from_city:f,to_city:t,date:d}) },
  weather: { query: (l,d,w) => api('POST','/weather/query',{location:l,date:d,forecast_days:w||7}) },
  plan: {
    generate: (r,w,u,t,opts) => api('POST','/plans/generate',{route_params:r,weather_data:w,user_params:u,ticket_data:t},opts),
    generateStream: (r,w,u,t,onEvent) => streamEvent('/plans/generate',{route_params:r,weather_data:w,user_params:u,ticket_data:t,stream:true},onEvent),
  },
  qa: {
    chat: (m) => api('POST','/qa/chat',{message:m}),
    chatStream: (m, onEvent) => streamEvent('/qa/chat',{message:m,stream:true},onEvent),
  },
  favorite: {
    add: (t,ti,c) => api('POST','/favorites/add',{fav_type:t,title:ti,content:c}),
    list: (t) => api('GET','/favorites/list'+(t?'?fav_type='+t:'')),
    delete: (id) => api('DELETE','/favorites/'+id),
    export: (t,c) => api('POST','/favorites/export/'+t,{content:c}),
  },
  forum: {
    categories: () => api('GET','/forum/categories'),
    listPosts: (catId, page) => {
      let url = '/forum/posts?page=' + (page||1) + '&page_size=20';
      if (catId) url += '&category_id=' + catId;
      return api('GET', url);
    },
    getPost: (id) => api('GET',`/forum/posts/${id}`),
    createPost: (data) => api('POST','/forum/posts',data),
    createReply: (postId, data) => api('POST',`/forum/posts/${postId}/replies`,data),
    deletePost: (id) => api('DELETE',`/forum/posts/${id}`),
    deleteReply: (id) => api('DELETE',`/forum/replies/${id}`),
    getReplies: (postId) => api('GET',`/forum/posts/${postId}/replies`),
    likeReply: (id) => api('POST',`/forum/replies/${id}/like`),
    likePost: (id) => api('POST',`/forum/posts/${id}/like`),
    pinPost: (id) => api('POST',`/forum/posts/${id}/pin`),
    createCategory: (data) => api('POST','/forum/categories',data),
    deleteCategory: (id) => api('DELETE',`/forum/categories/${id}`),
    uploadImage: async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);
      const opts = { method: 'POST', headers: {}, body: formData, signal: controller.signal };
      if (authToken) opts.headers['Authorization'] = 'Bearer ' + authToken;
      opts.headers['X-Session-Id'] = sessionId;
      let res, data;
      try {
        res = await fetch(API_BASE + '/forum/upload', opts);
        data = await res.json();
      } catch(e) {
        clearTimeout(timeoutId);
        if (e.name === 'AbortError') throw new Error('上传超时');
        throw e;
      }
      clearTimeout(timeoutId);
      if (!res.ok) throw new Error(data.detail || '上传失败');
      return data;
    },
  },
  moderation: {
    report: (data) => api('POST', '/moderation/report', data),
    queue: (params) => {
      let url = '/moderation/queue?status=' + (params?.status || 'pending');
      if (params?.type) url += '&target_type=' + params.type;
      return api('GET', url);
    },
    resolve: (id, action, ban) => api('POST', `/moderation/resolve/${id}`, { action, ban_user: !!ban }),
  },
};

function setToken(t){authToken=t;localStorage.setItem('token',t)}
function clearToken(){authToken='';localStorage.removeItem('token')}
function isLoggedIn(){return !!authToken}

// ====== SSE 流式消费器 ======
async function streamEvent(path, body, onEvent, timeout = 180000){
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  try {
    const res = await fetch(API_BASE + path, {
      method: 'POST', headers: apiHeaders(), body: JSON.stringify(body), signal: controller.signal
    });
    if (!res.ok) {
      const text = await res.text();
      let data;
      try { data = JSON.parse(text); } catch { data = {}; }
      throw new Error(data.detail || data.message || text || '请求失败');
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buf = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const chunk = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const line = chunk.split('\n').find(l => l.trim().startsWith('data:'));
        if (!line) continue;
        const data = line.slice(5).trim();
        if (data === '[DONE]') return;
        // 只容错 JSON 解析；onEvent 的异常（如 error 事件抛错）向上传播，让调用方感知失败
        let ev;
        try { ev = JSON.parse(data); } catch (e) { continue; }
        onEvent(ev);
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('请求超时，请检查网络连接');
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}
