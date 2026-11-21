function reupApp() {
  return {
    activeTab: 'dashboard',
    isSubmitting: false,
    isPublishing: false,
    showPublishModal: false,
    videoCacheBust: Date.now(),

    stats: {
      total_jobs: 0,
      completed_jobs: 0,
      failed_jobs: 0,
      processing_jobs: 0,
      facebook_published: 0,
      tiktok_published: 0
    },

    jobs: [],
    selectedJob: null,
    srtCues: [],
    liveLogs: [],

    newJob: {
      source_url: '',
      custom_product_hint: '',
      voice_code: '',
      auto_post_facebook: false,
      auto_post_tiktok: false
    },

    publishForm: {
      job_id: '',
      platform: 'facebook',
      title: '',
      caption: '',
      hashtags: '',
      publish_mode: 'reel'
    },

    configForm: {
      AI_BASE_URL: 'https://api.shopaikey.com/v1',
      AI_API_KEY: '',
      AI_MODEL: 'gpt-4o-mini',
      ASR_PROVIDER: 'shopaikey',
      ASR_API_KEY: '',
      ASR_BASE_URL: 'https://api.shopaikey.com/v1',
      ASR_MODEL: 'whisper-1',
      TTS_PROVIDER: 'vbee',
      VBEE_APP_ID: '63a47dd0-f273-4b4a-a9bf-ae354f38b554',
      VBEE_ACCESS_TOKEN: '',
      VBEE_REFRESH_TOKEN_COOKIE: '',
      VBEE_VOICE_CODE: 'hn_female_ngochuyen_full_48k-fhg',
      EDGE_TTS_VOICE: 'vi-VN-HoaiMyNeural',
      DOUYIN_COOKIE: '',
      SHOPEE_COOKIE: '',
      SHOPEE_SUB_ID: '',
      FACEBOOK_AUTO_PUBLISH: 'false',
      FACEBOOK_PAGE_ID: '',
      FACEBOOK_PAGE_ACCESS_TOKEN: '',
      FACEBOOK_PUBLISH_MODE: 'reel',
      TIKTOK_AUTO_PUBLISH: 'false',
      TIKTOK_SESSION_ID: '',
      TIKTOK_WEBHOOK_URL: ''
    },

    ws: null,

    async initApp() {
      await this.fetchStats();
      await this.fetchJobs();
      await this.fetchConfigs();
      await this.fetchLogs();
      this.connectWebSocket();

      setInterval(async () => {
        if (this.activeTab === 'dashboard') {
          await this.fetchJobs(false);
          await this.fetchStats();
        } else if (this.activeTab === 'logs') {
          await this.fetchLogs();
        }
      }, 4000);
    },

    statusSymbol(status) {
      if (status === 'COMPLETED') return '●';
      if (status === 'FAILED') return '✕';
      if (status === 'PENDING') return '○';
      return '◆';
    },

    formatTime(iso) {
      if (!iso) return '';
      try {
        const d = new Date(iso);
        return d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      } catch (e) {
        return '';
      }
    },

    parseSrtContent(raw) {
      if (!raw) return [];
      const blocks = raw.trim().replace(/\r\n/g, '\n').split(/\n\s*\n/);
      const cues = [];
      for (const b of blocks) {
        const lines = b.split('\n').map(l => l.trim()).filter(Boolean);
        if (lines.length >= 2) {
          const timeIdx = lines.findIndex(l => l.includes('-->'));
          if (timeIdx !== -1) {
            const timeLine = lines[timeIdx].replace(/,000/g, '').replace(/,\d+/g, '');
            const text = lines.slice(timeIdx + 1).join(' ');
            cues.push({
              index: cues.length + 1,
              time: timeLine,
              text: text
            });
          }
        }
      }
      return cues;
    },

    async selectJob(job) {
      this.selectedJob = job;
      this.videoCacheBust = Date.now();
      this.srtCues = [];
      if (job && job.id) {
        try {
          const res = await fetch(`/api/jobs/${job.id}/srt?t=${Date.now()}`);
          if (res.ok) {
            const text = await res.text();
            this.srtCues = this.parseSrtContent(text);
          }
        } catch (e) {
          console.warn('Chưa tải được file SRT:', e);
        }
      }
    },

    async fetchLogs() {
      try {
        const res = await fetch('/api/logs?limit=100');
        if (res.ok) {
          const data = await res.json();
          this.liveLogs = data.map(item => ({
            time: item.created_at ? new Date(item.created_at).toLocaleTimeString('vi-VN') : '',
            level: item.level || 'INFO',
            stage: item.stage || 'System',
            message: item.message || ''
          }));
        }
      } catch (e) {
        console.error('Lỗi tải logs:', e);
      }
    },

    connectWebSocket() {
      try {
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.ws = new WebSocket(`${proto}//${window.location.host}/ws/logs`);
        this.ws.onmessage = (event) => {
          try {
            const item = JSON.parse(event.data);
            this.liveLogs.push({
              time: item.created_at ? new Date(item.created_at).toLocaleTimeString('vi-VN') : new Date().toLocaleTimeString('vi-VN'),
              level: item.level || 'INFO',
              stage: item.stage || 'System',
              message: item.message || ''
            });
          } catch (err) {}
        };
      } catch (err) {
        console.warn('WebSocket không khả dụng, dùng HTTP polling fallback.');
      }
    },

    async fetchStats() {
      try {
        const res = await fetch('/api/stats');
        if (res.ok) {
          this.stats = await res.json();
        }
      } catch (e) {
        console.error('Lỗi tải thống kê:', e);
      }
    },

    async fetchJobs(autoSelectFirst = true) {
      try {
        const res = await fetch('/api/jobs');
        if (res.ok) {
          this.jobs = await res.json();
          if (this.selectedJob) {
            const updated = this.jobs.find(j => j.id === this.selectedJob.id);
            if (updated) {
              const prevStatus = this.selectedJob.status;
              this.selectedJob = updated;
              if (prevStatus !== 'COMPLETED' && updated.status === 'COMPLETED') {
                await this.selectJob(updated);
              }
            }
          } else if (autoSelectFirst && this.jobs.length > 0) {
            const firstCompleted = this.jobs.find(j => j.status === 'COMPLETED') || this.jobs[0];
            await this.selectJob(firstCompleted);
          }
        }
      } catch (e) {
        console.error('Lỗi tải danh sách job:', e);
      }
    },

    async fetchConfigs() {
      try {
        const res = await fetch('/api/configs/raw');
        if (res.ok) {
          const data = await res.json();
          for (const [key, obj] of Object.entries(data)) {
            if (this.configForm.hasOwnProperty(key)) {
              this.configForm[key] = obj.value || '';
            }
          }
        }
      } catch (e) {
        console.error('Lỗi tải cấu hình:', e);
      }
    },

    async submitJob() {
      if (!this.newJob.source_url.trim()) return;

      this.isSubmitting = true;
      try {
        const res = await fetch('/api/jobs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.newJob)
        });

        if (res.ok) {
          const job = await res.json();
          this.newJob.source_url = '';
          this.newJob.custom_product_hint = '';
          await this.fetchJobs(false);
          await this.selectJob(job);
          await this.fetchStats();
        } else {
          const err = await res.json();
          Swal.fire({
            icon: 'error',
            title: 'Không thể tạo tiến trình',
            text: err.detail || 'Vui lòng kiểm tra lại đường dẫn video'
          });
        }
      } catch (e) {
        Swal.fire({ icon: 'error', title: 'Lỗi kết nối', text: e.message });
      } finally {
        this.isSubmitting = false;
      }
    },

    async deleteJob(jobId) {
      const confirm = await Swal.fire({
        title: `Xóa tiến trình #${jobId}?`,
        text: 'Bản ghi tiến trình sẽ bị xóa khỏi danh sách.',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#a82020',
        cancelButtonColor: '#6e7b82',
        confirmButtonText: 'Xóa',
        cancelButtonText: 'Hủy'
      });

      if (!confirm.isConfirmed) return;

      try {
        const res = await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
        if (res.ok) {
          if (this.selectedJob && this.selectedJob.id === jobId) {
            this.selectedJob = null;
            this.srtCues = [];
          }
          await this.fetchJobs();
          await this.fetchStats();
        }
      } catch (e) {
        console.error('Lỗi xóa job:', e);
      }
    },

    async saveAllConfigs() {
      try {
        const res = await fetch('/api/configs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ configs: this.configForm })
        });

        if (res.ok) {
          Swal.fire({
            icon: 'success',
            title: 'Đã lưu cấu hình',
            text: 'Thông số Vbee, AI và Facebook đã được cập nhật vào cơ sở dữ liệu.',
            timer: 1800,
            showConfirmButton: false
          });
        } else {
          Swal.fire({ icon: 'error', title: 'Lỗi lưu', text: 'Không thể lưu cài đặt' });
        }
      } catch (e) {
        Swal.fire({ icon: 'error', title: 'Lỗi kết nối', text: e.message });
      }
    },

    async testConnection(target) {
      Swal.fire({
        title: `Đang kiểm tra ${target.toUpperCase()}...`,
        allowOutsideClick: false,
        didOpen: () => Swal.showLoading()
      });

      let params = {};
      if (target === 'facebook') {
        params = {
          page_id: this.configForm.FACEBOOK_PAGE_ID,
          page_token: this.configForm.FACEBOOK_PAGE_ACCESS_TOKEN
        };
      } else if (target === 'ai') {
        params = {
          base_url: this.configForm.AI_BASE_URL,
          api_key: this.configForm.AI_API_KEY,
          model: this.configForm.AI_MODEL
        };
      } else if (target === 'asr') {
        params = {
          provider: this.configForm.ASR_PROVIDER,
          base_url: this.configForm.ASR_BASE_URL,
          api_key: this.configForm.ASR_API_KEY,
          model: this.configForm.ASR_MODEL
        };
      } else if (target === 'vbee') {
        params = {
          app_id: this.configForm.VBEE_APP_ID,
          access_token: this.configForm.VBEE_ACCESS_TOKEN,
          cookie: this.configForm.VBEE_REFRESH_TOKEN_COOKIE
        };
      } else if (target === 'shopee') {
        params = {
          cookie: this.configForm.SHOPEE_COOKIE,
          sub_id: this.configForm.SHOPEE_SUB_ID
        };
      }

      try {
        const res = await fetch('/api/test-connection', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target: target, custom_params: params })
        });

        const data = await res.json();
        if (data.success) {
          let detail = data.message || 'Kết nối hợp lệ!';
          if (data.page_name) {
            detail += `\nFanpage: ${data.page_name} (ID: ${data.page_id})`;
          }
          Swal.fire({
            icon: 'success',
            title: 'Kết nối hoạt động tốt',
            text: detail
          });
        } else {
          Swal.fire({
            icon: 'error',
            title: 'Kết nối thất bại',
            text: data.error || 'Vui lòng kiểm tra lại token hoặc quyền truy cập'
          });
        }
      } catch (e) {
        Swal.fire({ icon: 'error', title: 'Lỗi', text: e.message });
      }
    },

    openPublishModal(job) {
      this.publishForm.job_id = job.id;
      this.publishForm.title = job.title || 'Video Review Sản Phẩm';
      this.publishForm.caption = job.caption || '';
      this.publishForm.hashtags = job.hashtags || '#xuhuong #review #douyin';
      this.publishForm.platform = 'facebook';
      this.publishForm.publish_mode = this.configForm.FACEBOOK_PUBLISH_MODE || 'reel';
      this.showPublishModal = true;
    },

    async submitManualPublish() {
      this.isPublishing = true;
      try {
        const res = await fetch(`/api/jobs/${this.publishForm.job_id}/publish`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.publishForm)
        });

        const data = await res.json();
        if (res.ok && data.success) {
          Swal.fire({
            icon: 'success',
            title: 'Đã xuất bản thành công',
            text: data.message || `Đã đăng video #${this.publishForm.job_id}`
          });
          this.showPublishModal = false;
          await this.fetchJobs(false);
          await this.fetchStats();
        } else {
          Swal.fire({
            icon: 'error',
            title: 'Lỗi xuất bản',
            text: data.detail || data.error || 'Không thể đăng video'
          });
        }
      } catch (e) {
        Swal.fire({ icon: 'error', title: 'Lỗi kết nối', text: e.message });
      } finally {
        this.isPublishing = false;
      }
    }
  };
}
