function reupApp() {
  return {
    activeTab: 'dashboard',
    isSubmitting: false,
    isPublishing: false,
    showAdvanced: false,
    showPublishModal: false,
    showPreviewModal: false,
    videoCacheBust: Date.now(),
    isPlayingVbee: false,
    latestCompletedJobId: '',
    vbeeCurrentTime: '48kHz PCM',
    vbeeCurrentCaption: '',
    isBatchMode: false,
    batchUrlsText: '',
    affTestInput: 'quạt tích điện cầm tay mini',
    affTestResult: null,
    isTestingAff: false,

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
      SHOPEE_APP_ID: '',
      SHOPEE_APP_SECRET: '',
      SHOPEE_COOKIE: '',
      SHOPEE_SUB_ID: '16550927460',
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
      this.refreshIcons();

      setInterval(async () => {
        if (this.activeTab === 'dashboard' || this.activeTab === 'jobs') {
          await this.fetchJobs(false);
          await this.fetchStats();
        } else if (this.activeTab === 'logs') {
          await this.fetchLogs();
        }
      }, 4000);
    },

    refreshIcons() {
      this.$nextTick(() => {
        if (window.lucide) {
          window.lucide.createIcons();
        }
      });
    },

    isStageRunning(stages) {
      if (!this.jobs || this.jobs.length === 0) return false;
      return this.jobs.some(j => stages.includes(j.status));
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
            const text = lines.slice(timeIdx + 1).join(' ');
            cues.push({
              index: cues.length + 1,
              time: lines[timeIdx],
              text: text
            });
          }
        }
      }
      return cues;
    },

    async openPreviewModal(job) {
      this.selectedJob = job;
      this.videoCacheBust = Date.now();
      this.srtCues = [];
      this.showPreviewModal = true;
      this.refreshIcons();
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

    async fetchJobs(refreshUi = true) {
      try {
        const res = await fetch('/api/jobs');
        if (res.ok) {
          this.jobs = await res.json();
          const completed = this.jobs.find(j => j.status === 'COMPLETED');
          if (completed && completed.id !== this.latestCompletedJobId) {
            this.latestCompletedJobId = completed.id;
            this.loadLatestVbeeSrt(completed.id);
          }
          if (refreshUi) this.refreshIcons();
        }
      } catch (e) {
        console.error('Lỗi tải danh sách job:', e);
      }
    },

    srtTimeToSeconds(tStr) {
      if (!tStr) return 0;
      const parts = tStr.trim().replace(',', '.').split(':');
      if (parts.length !== 3) return 0;
      return parseFloat(parts[0]) * 3600 + parseFloat(parts[1]) * 60 + parseFloat(parts[2]);
    },

    async loadLatestVbeeSrt(jobId) {
      try {
        const res = await fetch(`/api/jobs/${jobId}/srt?t=${Date.now()}`);
        if (res.ok) {
          const text = await res.text();
          this.vbeeCues = this.parseSrtContent(text).map(c => {
            const [s, e] = c.time.split('-->');
            return {
              ...c,
              startSec: this.srtTimeToSeconds(s),
              endSec: this.srtTimeToSeconds(e)
            };
          });
          if (this.vbeeCues.length > 0 && !this.vbeeCurrentCaption) {
            this.vbeeCurrentCaption = `"${this.vbeeCues[0].text}"`;
          }
        }
      } catch (e) {}
    },

    toggleVbeeAudioPreview() {
      const player = this.$refs.vbeeAudioPlayer;
      if (!player) return;

      const targetJobId = this.latestCompletedJobId || (this.jobs.find(j => j.status === 'COMPLETED') || {}).id;
      if (!targetJobId) {
        Swal.fire({
          icon: 'info',
          title: 'Chưa có file âm thanh',
          text: 'Hãy chạy ít nhất 1 video hoàn chỉnh để nghe bản thu Vbee.'
        });
        return;
      }

      const expectedSrc = `/api/jobs/${targetJobId}/audio`;
      if (!player.src || !player.src.includes(expectedSrc)) {
        player.src = `${expectedSrc}?t=${Date.now()}`;
        player.ontimeupdate = () => {
          const cur = player.currentTime || 0;
          const mins = String(Math.floor(cur / 60)).padStart(2, '0');
          const secs = String(Math.floor(cur % 60)).padStart(2, '0');
          this.vbeeCurrentTime = `${mins}:${secs}`;
          if (this.vbeeCues && this.vbeeCues.length > 0) {
            const active = this.vbeeCues.find(c => cur >= c.startSec && cur <= c.endSec + 0.4);
            if (active) {
              this.vbeeCurrentCaption = `"${active.text}"`;
            }
          }
        };
      }

      if (player.paused) {
        player.play().catch(err => console.error('Audio play error:', err));
      } else {
        player.pause();
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
          Swal.fire({
            icon: 'success',
            title: 'Đã đưa vào hàng đợi!',
            text: `Mã tiến trình: #${job.id}`,
            timer: 2000,
            showConfirmButton: false,
            background: '#0f172a',
            color: '#fff'
          });
          this.newJob.source_url = '';
          this.newJob.custom_product_hint = '';
          await this.fetchJobs();
          await this.fetchStats();
        } else {
          const err = await res.json();
          Swal.fire({
            icon: 'error',
            title: 'Lỗi tạo job',
            text: err.detail || 'Không thể gửi yêu cầu',
            background: '#0f172a',
            color: '#fff'
          });
        }
      } catch (e) {
        Swal.fire({ icon: 'error', title: 'Lỗi kết nối', text: e.message, background: '#0f172a', color: '#fff' });
      } finally {
        this.isSubmitting = false;
        this.refreshIcons();
      }
    },

    async submitBatchJobs() {
      const urls = (this.batchUrlsText || '')
        .split(/\r?\n/)
        .map(u => u.trim())
        .filter(Boolean);
      if (urls.length === 0) return;

      this.isSubmitting = true;
      try {
        const res = await fetch('/api/jobs/batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            urls: urls,
            custom_product_hint: this.newJob.custom_product_hint,
            voice_code: this.newJob.voice_code,
            auto_post_facebook: this.newJob.auto_post_facebook,
            auto_post_tiktok: this.newJob.auto_post_tiktok
          })
        });

        if (res.ok) {
          const data = await res.json();
          Swal.fire({
            icon: 'success',
            title: `Đã nạp ${data.count} video vào hàng đợi!`,
            text: 'Hệ thống đang xử lý đồng thời và đồng bộ trạng thái thời gian thực.',
            timer: 2200,
            showConfirmButton: false,
            background: '#0f172a',
            color: '#fff'
          });
          this.batchUrlsText = '';
          await this.fetchJobs();
          await this.fetchStats();
        } else {
          const err = await res.json();
          Swal.fire({
            icon: 'error',
            title: 'Lỗi nạp batch',
            text: err.detail || 'Không thể nạp danh sách video',
            background: '#0f172a',
            color: '#fff'
          });
        }
      } catch (e) {
        Swal.fire({ icon: 'error', title: 'Lỗi kết nối', text: e.message, background: '#0f172a', color: '#fff' });
      } finally {
        this.isSubmitting = false;
      }
    },

    async runAffiliateAgentTest() {
      if (!this.affTestInput.trim()) return;
      this.isTestingAff = true;
      try {
        const res = await fetch('/api/affiliate/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            keyword_or_url: this.affTestInput.trim(),
            sub_id: this.configForm.SHOPEE_SUB_ID || '16550927460'
          })
        });
        if (res.ok) {
          this.affTestResult = await res.json();
        }
      } catch (e) {
        console.error('Lỗi test affiliate:', e);
      } finally {
        this.isTestingAff = false;
      }
    },

    async verifyJobAffiliate(job) {
      if (!job || !job.id) return;
      try {
        const res = await fetch(`/api/jobs/${job.id}/verify-affiliate`, { method: 'POST' });
        if (res.ok) {
          const data = await res.json();
          await this.fetchJobs(false);
          Swal.fire({
            icon: 'success',
            title: 'Affiliate Agent đã kiểm tra!',
            html: `<div style="text-align:left;font-size:12.5px;line-height:1.6;">
              <div><b>Sản phẩm:</b> ${data.product_keyword}</div>
              <div><b>Phương thức:</b> <code>${data.method}</code> (Sub-ID: <code>${data.sub_id}</code>)</div>
              <div style="margin-top:6px;"><b>Link Affiliate:</b><br><a href="${data.affiliate_link}" target="_blank" style="color:#dafa9c;word-break:break-all;">${data.affiliate_link}</a></div>
            </div>`,
            background: '#0f172a',
            color: '#fff'
          });
        }
      } catch (e) {
        Swal.fire({ icon: 'error', title: 'Lỗi kiểm tra Affiliate', text: e.message, background: '#0f172a', color: '#fff' });
      }
    },

    async deleteJob(jobId) {
      const confirm = await Swal.fire({
        title: 'Xóa video này?',
        text: 'Dữ liệu và file video sẽ bị xóa vĩnh viễn',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#ef4444',
        cancelButtonColor: '#334155',
        confirmButtonText: 'Xóa ngay',
        cancelButtonText: 'Hủy',
        background: '#0f172a',
        color: '#fff'
      });

      if (!confirm.isConfirmed) return;

      try {
        const res = await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
        if (res.ok) {
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
            title: 'Đã lưu cấu hình!',
            text: 'Mọi token và endpoint đã được cập nhật trực tiếp vào cơ sở dữ liệu.',
            timer: 2000,
            showConfirmButton: false,
            background: '#0f172a',
            color: '#fff'
          });
        } else {
          Swal.fire({ icon: 'error', title: 'Lỗi lưu', text: 'Không thể lưu cài đặt', background: '#0f172a', color: '#fff' });
        }
      } catch (e) {
        Swal.fire({ icon: 'error', title: 'Lỗi kết nối', text: e.message, background: '#0f172a', color: '#fff' });
      }
    },

    async testConnection(target) {
      Swal.fire({
        title: `Đang kiểm tra kết nối ${target.toUpperCase()}...`,
        allowOutsideClick: false,
        didOpen: () => Swal.showLoading(),
        background: '#0f172a',
        color: '#fff'
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
          sub_id: this.configForm.SHOPEE_SUB_ID,
          app_id: this.configForm.SHOPEE_APP_ID,
          app_secret: this.configForm.SHOPEE_APP_SECRET
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
          let detail = data.message || 'Kết nối thành công!';
          if (data.page_name) {
            detail += `\nFanpage: ${data.page_name} (ID: ${data.page_id})`;
          }
          Swal.fire({
            icon: 'success',
            title: 'Kết nối thành công!',
            text: detail,
            background: '#0f172a',
            color: '#fff'
          });
        } else {
          Swal.fire({
            icon: 'error',
            title: 'Kết nối thất bại',
            text: data.error || 'Vui lòng kiểm tra lại token hoặc quyền hạn',
            background: '#0f172a',
            color: '#fff'
          });
        }
      } catch (e) {
        Swal.fire({ icon: 'error', title: 'Lỗi', text: e.message, background: '#0f172a', color: '#fff' });
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
      this.refreshIcons();
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
            title: 'Đã xuất bản thành công!',
            text: data.message || `Đã đăng video #${this.publishForm.job_id}`,
            background: '#0f172a',
            color: '#fff'
          });
          this.showPublishModal = false;
          await this.fetchJobs();
          await this.fetchStats();
        } else {
          Swal.fire({
            icon: 'error',
            title: 'Lỗi xuất bản',
            text: data.detail || data.error || 'Không thể đăng video',
            background: '#0f172a',
            color: '#fff'
          });
        }
      } catch (e) {
        Swal.fire({ icon: 'error', title: 'Lỗi kết nối', text: e.message, background: '#0f172a', color: '#fff' });
      } finally {
        this.isPublishing = false;
      }
    }
  };
}
