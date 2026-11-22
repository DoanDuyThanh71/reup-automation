import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Loop,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

/*
  Founder's Empathy Story + Live Revenue/Views Dopamine Commercial (36s = 1080 frames @ 30fps)
  Arc:
  1. 0.0s - 8.0s   (0 - 240):    THE CONFESSION ("Tôi không làm tool để đi bán — Tôi cũng từng thức 3h sáng âm tiền như bạn")
  2. 8.0s - 16.0s  (240 - 480):  THE SELF-RESCUE ("Tự viết bản .EXE khóa xưng hô + Ngọc Huyền Vbee / 0đ để cứu dàn kênh của mình")
  3. 16.0s - 27.0s (480 - 810):  THE DOPAMINE PAYOFF (Live Facebook Content Monetization $1,640.50 Paid + 4.86M Views + Shopee Orders!)
  4. 27.0s - 36.0s (810 - 1080): PEER-TO-PEER INVITATION ("Tặng bản .EXE 0đ cho anh em cùng cảnh ngộ • Buổi Meet 50k chia sẻ thật")
*/

const C = {
  bg: '#050507',
  glass: 'rgba(13, 15, 21, 0.86)',
  ink: '#f6f6f3',
  muted: '#a0a4b0',
  accent: '#dafa9c',
  accentInk: '#080b04',
  fbBlue: '#1877F2',
  green: '#22c55e',
  shopee: '#ee4d2d',
  red: '#ff5c5c',
  border: 'rgba(255,255,255,0.15)',
};

const FONT = '"Plus Jakarta Sans", "Segoe UI", system-ui, sans-serif';
const MONO = '"Geist Mono", "Consolas", monospace';

const CinemaFrame: React.FC<{flash?: boolean}> = ({flash = true}) => {
  const frame = useCurrentFrame();
  const fl = flash ? interpolate(frame, [0, 9], [0.45, 0], {extrapolateRight: 'clamp'}) : 0;
  return (
    <>
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(circle at 50% 45%, rgba(0,0,0,0.08) 0%, rgba(5,5,8,0.6) 76%, rgba(2,2,4,0.92) 100%)',
          pointerEvents: 'none',
        }}
      />
      <div style={{position: 'absolute', top: 0, left: 0, right: 0, height: 24, background: '#000', zIndex: 30}} />
      <div style={{position: 'absolute', bottom: 0, left: 0, right: 0, height: 24, background: '#000', zIndex: 30}} />
      {fl > 0.01 && (
        <AbsoluteFill
          style={{
            background: `rgba(255,255,255,${fl})`,
            mixBlendMode: 'overlay',
            pointerEvents: 'none',
            zIndex: 25,
          }}
        />
      )}
    </>
  );
};

const SubtitlePill: React.FC<{text: string; accentWord?: string}> = ({text, accentWord}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const pop = spring({frame, fps, config: {damping: 18, stiffness: 170}});
  const parts = accentWord ? text.split(accentWord) : [text];

  return (
    <div
      style={{
        position: 'absolute',
        bottom: 40,
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'center',
        zIndex: 28,
      }}
    >
      <div
        style={{
          opacity: pop,
          transform: `translateY(${interpolate(pop, [0, 1], [12, 0])}px)`,
          padding: '10px 26px',
          borderRadius: 999,
          background: 'rgba(6, 7, 10, 0.88)',
          backdropFilter: 'blur(16px)',
          border: '1px solid rgba(218,250,156,0.35)',
          color: C.ink,
          fontFamily: FONT,
          fontSize: 19,
          fontWeight: 600,
          boxShadow: '0 14px 40px rgba(0,0,0,0.8)',
        }}
      >
        {accentWord && parts.length > 1 ? (
          <>
            {parts[0]}
            <span style={{color: C.accent, fontWeight: 800}}>{accentWord}</span>
            {parts.slice(1).join(accentWord)}
          </>
        ) : (
          text
        )}
      </div>
    </div>
  );
};

/* ============================================================================
   ACT 1 (0 - 240 frames / 0.0s - 8.0s): FOUNDER'S EMPATHY CONFESSION
   ============================================================================ */
const Act1FounderConfession: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const zoom = interpolate(frame, [0, 240], [1.02, 1.14]);
  const lossVnd = Math.round(interpolate(frame, [45, 165], [450000, 2850000], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}));
  const cardIn = spring({frame: frame - 35, fps, config: {damping: 15}});

  return (
    <AbsoluteFill style={{backgroundColor: C.bg, fontFamily: FONT}}>
      <AbsoluteFill style={{transform: `scale(${zoom})`}}>
        <OffthreadVideo
          src={staticFile('broll_pain.mp4')}
          muted
          style={{width: '100%', height: '100%', objectFit: 'cover', filter: 'brightness(0.62) contrast(1.12) saturate(0.85)'}}
        />
      </AbsoluteFill>
      <CinemaFrame flash={false} />

      <AbsoluteFill style={{padding: '68px 80px', justifyContent: 'center', zIndex: 20}}>
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 10,
            alignSelf: 'flex-start',
            padding: '6px 14px',
            borderRadius: 999,
            background: 'rgba(255,255,255,0.08)',
            border: `1px solid ${C.border}`,
            color: C.accent,
            fontSize: 14,
            fontWeight: 700,
            marginBottom: 18,
          }}
        >
          TÂM SỰ THẬT TỪ NGƯỜI CÀY KÊNH MỘT MÌNH • 02:45 AM
        </div>

        <h1
          style={{
            margin: 0,
            color: C.ink,
            fontSize: 52,
            fontWeight: 800,
            lineHeight: 1.12,
            letterSpacing: '-0.03em',
            maxWidth: 880,
            textShadow: '0 12px 36px rgba(0,0,0,0.9)',
          }}
        >
          “Tôi làm ra tool này{' '}
          <span style={{color: C.accent}}>không phải để đi bán phần mềm.</span>
          <br />
          Tôi cũng từng kiệt sức lúc 3h sáng như bạn.”
        </h1>

        {/* Draining Cost vs $0 Revenue Pain Card */}
        <div
          style={{
            marginTop: 28,
            opacity: cardIn,
            transform: `translateY(${interpolate(cardIn, [0, 1], [24, 0])}px)`,
            display: 'inline-flex',
            gap: 18,
            alignSelf: 'flex-start',
          }}
        >
          <div
            style={{
              padding: '16px 24px',
              borderRadius: 16,
              background: 'rgba(20, 10, 12, 0.86)',
              backdropFilter: 'blur(16px)',
              border: '1px solid rgba(255, 92, 92, 0.45)',
            }}
          >
            <div style={{color: '#ff9c9c', fontSize: 13, fontWeight: 700, fontFamily: MONO}}>
              CHI PHÍ MUA KÝ TỰ VOICE & TOKEN LÚC MỚI XÂY KÊNH
            </div>
            <div style={{color: C.red, fontSize: 34, fontWeight: 800, marginTop: 4, fontFamily: MONO}}>
              -{lossVnd.toLocaleString('vi-VN')}đ / tháng
            </div>
          </div>

          <div
            style={{
              padding: '16px 24px',
              borderRadius: 16,
              background: C.glass,
              backdropFilter: 'blur(16px)',
              border: `1px solid ${C.border}`,
            }}
          >
            <div style={{color: C.muted, fontSize: 13, fontWeight: 700, fontFamily: MONO}}>
              DOANH THU KHI BỊ DÍNH QUÉT TRÙNG & LOẠN VAI
            </div>
            <div style={{color: C.ink, fontSize: 34, fontWeight: 800, marginTop: 4, fontFamily: MONO}}>
              0đ • 84 lượt xem
            </div>
          </div>
        </div>
      </AbsoluteFill>

      <SubtitlePill
        text="“Kênh chưa kiếm được đồng nào đã âm tiền triệu mua giọng đọc & thức trắng sửa phụ đề...”"
        accentWord="âm tiền triệu"
      />
    </AbsoluteFill>
  );
};

/* ============================================================================
   ACT 2 (240 - 480 frames / 8.0s - 16.0s): WHY I BUILT THIS .EXE FOR MYSELF
   ============================================================================ */
const Act2SelfRescue: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({frame, fps, config: {damping: 16, stiffness: 95}});
  const rotY = interpolate(frame, [0, 240], [-13, -4]);

  return (
    <AbsoluteFill style={{backgroundColor: C.bg, fontFamily: FONT, perspective: 1400}}>
      <OffthreadVideo
        src={staticFile('broll_voice.mp4')}
        muted
        style={{width: '100%', height: '100%', objectFit: 'cover', filter: 'brightness(0.5) contrast(1.14)'}}
      />
      <CinemaFrame />

      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', zIndex: 20}}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 36,
            transformStyle: 'preserve-3d',
            transform: `scale(${interpolate(enter, [0, 1], [0.88, 1])}) rotateY(${rotY}deg)`,
          }}
        >
          <div
            style={{
              width: 680,
              padding: 30,
              borderRadius: 24,
              background: C.glass,
              backdropFilter: 'blur(24px)',
              border: `1px solid ${C.border}`,
              boxShadow: '0 40px 90px rgba(0,0,0,0.85)',
            }}
          >
            <div style={{color: C.accent, fontFamily: MONO, fontSize: 13, fontWeight: 800}}>
              LÝ DO RA ĐỜI REUP STUDIO .EXE
            </div>
            <h2 style={{margin: '8px 0 16px', color: C.ink, fontSize: 34, fontWeight: 800, lineHeight: 1.15}}>
              Tôi tự đóng gói quy trình cứu dàn kênh của chính mình vào 1 cú Click.
            </h2>

            <div style={{display: 'grid', gap: 11}}>
              <div style={{padding: '13px 16px', borderRadius: 14, background: 'rgba(218,250,156,0.1)', border: '1px solid rgba(218,250,156,0.4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                <div>
                  <div style={{color: C.ink, fontWeight: 700, fontSize: 16}}>✓ Tự xem hết 10 phút phim khóa chặt xưng hô</div>
                  <div style={{color: C.muted, fontSize: 13}}>Không còn cảnh đầu phim gọi Chủ tịch, cuối phim xưng Mày - Tao</div>
                </div>
                <span style={{color: C.accent, fontFamily: MONO, fontSize: 12, fontWeight: 800}}>AI 2 TẦNG</span>
              </div>

              <div style={{padding: '13px 16px', borderRadius: 14, background: 'rgba(255,255,255,0.05)', border: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                <div>
                  <div style={{color: C.ink, fontWeight: 700, fontSize: 16}}>✓ Giọng Ngọc Huyền Vbee + Dàn Voice 0đ chia 5 Model</div>
                  <div style={{color: C.muted, fontSize: 13}}>Cày 300 clip/ngày bằng Key miễn phí + Chạy Offline không tốn tiền</div>
                </div>
                <span style={{color: C.green, fontFamily: MONO, fontSize: 12, fontWeight: 800}}>0đ PHÍ THÁNG</span>
              </div>

              <div style={{padding: '13px 16px', borderRadius: 14, background: 'rgba(255,255,255,0.05)', border: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                <div>
                  <div style={{color: C.ink, fontWeight: 700, fontSize: 16}}>✓ Làm mới vân tay khung hình MP4 tự động</div>
                  <div style={{color: C.muted, fontSize: 13}}>Vượt quét trùng lặp bản quyền Reels & TikTok</div>
                </div>
                <span style={{color: C.accent, fontFamily: MONO, fontSize: 12, fontWeight: 800}}>SẠCH HASH</span>
              </div>
            </div>
          </div>

          {/* Real Review-Phim Phone Output */}
          <div
            style={{
              width: 244,
              height: 432,
              borderRadius: 34,
              padding: 9,
              background: 'linear-gradient(145deg, #3a3d46, #14161b)',
              boxShadow: '0 36px 80px rgba(0,0,0,0.9)',
            }}
          >
            <div style={{width: '100%', height: '100%', borderRadius: 26, overflow: 'hidden', position: 'relative', background: '#000'}}>
              <OffthreadVideo src={staticFile('reup_real_preview.mp4')} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
              <div style={{position: 'absolute', top: 12, left: 12, right: 12, padding: '5px 8px', borderRadius: 999, background: 'rgba(0,0,0,0.75)', color: C.accent, fontSize: 11, fontWeight: 800, textAlign: 'center'}}>
                ● THÀNH PHẨM TỰ ĐỘNG
              </div>
            </div>
          </div>
        </div>
      </AbsoluteFill>

      <SubtitlePill
        text="“Tôi tự viết bản .EXE này để giải phóng chính mình khỏi cảnh cắt sửa thủ công.”"
        accentWord="giải phóng chính mình"
      />
    </AbsoluteFill>
  );
};

/* ============================================================================
   ACT 3 (480 - 810 frames / 16.0s - 27.0s): THE DOPAMINE EXPLOSION
   LIVE FACEBOOK CONTENT MONETIZATION PAYOUT ($) + 4.86M VIEWS + SHOPEE ORDERS!
   ============================================================================ */
const Act3FacebookPayoutAndViews: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  // Animated Counters
  const views = Math.round(
    interpolate(frame, [8, 135], [142000, 4862400], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})
  );
  const fbUsd = interpolate(frame, [20, 155], [48.5, 1642.8], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const fbVnd = Math.round(fbUsd * 25400);
  const shopeeVnd = Math.round(
    interpolate(frame, [60, 180], [650000, 8950000], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})
  );

  // Chart reveal progress (0 -> 1)
  const chartProg = interpolate(frame, [10, 140], [0.08, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  // Floating Payout Notification Toasts synced with our audio chimes (16.6s -> f=18, 19.4s -> f=102, 22.2s -> f=186)
  const toasts = [
    {at: 16, icon: 'f', color: C.fbBlue, title: 'Meta Content Monetization • Paid', body: 'Thanh toán +$1,642.80 (≈ 41,7 Triệu đ) từ Facebook Reels'},
    {at: 96, icon: '▶', color: C.green, title: 'Đề xuất cắn xu hướng Reels', body: 'Tập 14 đạt +1.420.000 lượt phát chỉ sau 48 giờ'},
    {at: 174, icon: 'S', color: C.shopee, title: 'Shopee Affiliate Auto-Comment', body: '+214 đơn hàng mới từ link ghim bình luận đầu'},
  ];

  return (
    <AbsoluteFill style={{backgroundColor: C.bg, fontFamily: FONT, perspective: 1300}}>
      <Loop durationInFrames={235}>
        <OffthreadVideo
          src={staticFile('broll_payoff.mp4')}
          muted
          style={{width: '100%', height: '100%', objectFit: 'cover', filter: 'brightness(0.48) contrast(1.12)'}}
        />
      </Loop>
      <CinemaFrame />

      <AbsoluteFill style={{padding: '54px 68px', justifyContent: 'center', zIndex: 20}}>
        <div style={{display: 'grid', gridTemplateColumns: '1.22fr 0.78fr', gap: 28, alignItems: 'center'}}>
          {/* LEFT: 3D Facebook Professional / Content Monetization Payout Dashboard */}
          <div
            style={{
              padding: 28,
              borderRadius: 24,
              background: 'rgba(11, 14, 22, 0.9)',
              backdropFilter: 'blur(24px)',
              border: '1px solid rgba(24, 119, 242, 0.45)',
              boxShadow: '0 36px 90px rgba(0,0,0,0.85), 0 0 48px rgba(24, 119, 242, 0.22)',
              transform: `rotateY(${interpolate(frame, [0, 330], [7, 2])}deg)`,
            }}
          >
            {/* Header */}
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18}}>
              <div style={{display: 'flex', alignItems: 'center', gap: 10}}>
                <div
                  style={{
                    width: 34,
                    height: 34,
                    borderRadius: 10,
                    background: C.fbBlue,
                    color: '#fff',
                    display: 'grid',
                    placeItems: 'center',
                    fontWeight: 900,
                    fontSize: 20,
                  }}
                >
                  f
                </div>
                <div>
                  <div style={{color: C.ink, fontWeight: 800, fontSize: 16}}>Bảng điều khiển Kiếm tiền Facebook Reels</div>
                  <div style={{color: C.muted, fontSize: 12}}>28 ngày qua • Hệ thống 5 Fanpage chạy tự động</div>
                </div>
              </div>
              <span
                style={{
                  padding: '5px 12px',
                  borderRadius: 999,
                  background: 'rgba(34,197,94,0.18)',
                  border: '1px solid rgba(34,197,94,0.5)',
                  color: C.green,
                  fontSize: 12,
                  fontWeight: 800,
                  fontFamily: MONO,
                }}
              >
                ● ĐÃ THANH TOÁN (PAID)
              </span>
            </div>

            {/* 2 Giant Metric Boxes: Facebook $ Payout & Total Reels Views */}
            <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 18}}>
              <div
                style={{
                  padding: '16px 18px',
                  borderRadius: 16,
                  background: 'linear-gradient(135deg, rgba(24,119,242,0.18), rgba(34,197,94,0.12))',
                  border: '1px solid rgba(34,197,94,0.45)',
                }}
              >
                <div style={{color: '#93c5fd', fontSize: 12, fontWeight: 700, fontFamily: MONO}}>
                  TIỀN FACEBOOK TRẢ (REELS BONUS)
                </div>
                <div style={{color: '#4ade80', fontSize: 40, fontWeight: 800, marginTop: 4, fontFamily: MONO, letterSpacing: '-0.03em'}}>
                  ${fbUsd.toFixed(2)}
                </div>
                <div style={{color: C.ink, fontSize: 14, fontWeight: 700, marginTop: 2}}>
                  ≈ +{fbVnd.toLocaleString('vi-VN')} VNĐ
                </div>
              </div>

              <div
                style={{
                  padding: '16px 18px',
                  borderRadius: 16,
                  background: 'rgba(255,255,255,0.04)',
                  border: `1px solid ${C.border}`,
                }}
              >
                <div style={{color: C.muted, fontSize: 12, fontWeight: 700, fontFamily: MONO}}>
                  LƯỢT XEM REELS ĐỔ VỀ
                </div>
                <div style={{color: C.ink, fontSize: 36, fontWeight: 800, marginTop: 6, fontFamily: MONO, letterSpacing: '-0.03em'}}>
                  {views.toLocaleString('en-US')}
                </div>
                <div style={{color: C.green, fontSize: 13, fontWeight: 700, marginTop: 4}}>
                  ▲ +812% so với làm thủ công
                </div>
              </div>
            </div>

            {/* Animated Growth Curve SVG + Shopee Bonus Bar */}
            <div
              style={{
                padding: '14px 16px',
                borderRadius: 14,
                background: 'rgba(0,0,0,0.45)',
                border: `1px solid ${C.border}`,
              }}
            >
              <svg viewBox="0 0 520 86" style={{width: '100%', height: 74, overflow: 'visible'}}>
                <defs>
                  <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22c55e" stopOpacity="0.45" />
                    <stop offset="100%" stopColor="#22c55e" stopOpacity="0.0" />
                  </linearGradient>
                  <clipPath id="revealClip">
                    <rect x="0" y="0" width={520 * chartProg} height="90" />
                  </clipPath>
                </defs>
                <g clipPath="url(#revealClip)">
                  <path
                    d="M0 78 C70 74, 120 68, 180 56 C240 44, 290 48, 350 28 C410 12, 465 10, 520 4 L520 86 L0 86 Z"
                    fill="url(#revGrad)"
                  />
                  <path
                    d="M0 78 C70 74, 120 68, 180 56 C240 44, 290 48, 350 28 C410 12, 465 10, 520 4"
                    fill="none"
                    stroke="#4ade80"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                  />
                </g>
              </svg>
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6, fontSize: 14}}>
                <span style={{color: C.muted}}>+ Hoa hồng bình luận Shopee tự động:</span>
                <strong style={{color: '#ff8a65', fontFamily: MONO, fontSize: 17}}>
                  +{shopeeVnd.toLocaleString('vi-VN')} VNĐ
                </strong>
              </div>
            </div>
          </div>

          {/* RIGHT: Stacking Live Notification Toasts + 0đ Operating Cost */}
          <div style={{display: 'grid', gap: 14}}>
            {toasts.map((t, idx) => {
              const p = spring({frame: frame - t.at, fps, config: {damping: 13, stiffness: 160}});
              return (
                <div
                  key={idx}
                  style={{
                    opacity: p,
                    transform: `translateX(${interpolate(p, [0, 1], [48, 0])}px) scale(${interpolate(p, [0, 1], [0.92, 1])})`,
                    padding: '15px 18px',
                    borderRadius: 18,
                    background: C.glass,
                    backdropFilter: 'blur(20px)',
                    border: `1px solid ${C.border}`,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 14,
                    boxShadow: '0 20px 44px rgba(0,0,0,0.65)',
                  }}
                >
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: 12,
                      background: t.color,
                      color: '#fff',
                      display: 'grid',
                      placeItems: 'center',
                      fontWeight: 900,
                      fontSize: 18,
                      flexShrink: 0,
                    }}
                  >
                    {t.icon}
                  </div>
                  <div>
                    <div style={{color: C.ink, fontWeight: 800, fontSize: 15}}>{t.title}</div>
                    <div style={{color: C.muted, fontSize: 13, marginTop: 2}}>{t.body}</div>
                  </div>
                </div>
              );
            })}

            <div
              style={{
                padding: '16px 20px',
                borderRadius: 18,
                background: 'rgba(218,250,156,0.12)',
                border: '1px solid rgba(218,250,156,0.45)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <span style={{color: C.ink, fontSize: 15, fontWeight: 700}}>Chi phí API & Voice tháng này:</span>
              <span style={{color: C.accent, fontFamily: MONO, fontSize: 26, fontWeight: 900}}>0đ</span>
            </div>
          </div>
        </div>
      </AbsoluteFill>

      <SubtitlePill
        text="“Hàng triệu view đổ về, tiền Facebook trả đều mỗi tháng, trong khi chi phí nuôi AI bằng 0đ.”"
        accentWord="tiền Facebook trả đều"
      />
    </AbsoluteFill>
  );
};

/* ============================================================================
   ACT 4 (810 - 1080 frames / 27.0s - 36.0s): SINCERE PEER-TO-PEER INVITATION
   ============================================================================ */
const Act4PeerInviteCTA: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const pop = spring({frame, fps, config: {damping: 14, stiffness: 120}});
  const pulse = 1 + Math.sin(frame * 0.2) * 0.025;

  return (
    <AbsoluteFill style={{backgroundColor: C.bg, fontFamily: FONT}}>
      <Loop durationInFrames={235}>
        <OffthreadVideo
          src={staticFile('broll_neural.mp4')}
          muted
          style={{width: '100%', height: '100%', objectFit: 'cover', filter: 'brightness(0.36) contrast(1.2)'}}
        />
      </Loop>
      <CinemaFrame />

      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', textAlign: 'center', zIndex: 22, padding: '0 64px'}}>
        <div style={{opacity: pop, transform: `scale(${interpolate(pop, [0, 1], [0.92, 1])})`, maxWidth: 980}}>
          <div
            style={{
              display: 'inline-block',
              padding: '7px 18px',
              borderRadius: 999,
              background: 'rgba(218,250,156,0.16)',
              border: '1px solid rgba(218,250,156,0.45)',
              color: C.accent,
              fontFamily: MONO,
              fontSize: 14,
              fontWeight: 800,
              marginBottom: 18,
            }}
          >
            DÀNH CHO ANH EM CÙNG CẢNH NGỘ CÀY KÊNH MỘT MÌNH
          </div>

          <h2 style={{margin: 0, color: C.ink, fontSize: 54, fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.1}}>
            Tôi tặng sẵn bản .EXE miễn phí để bạn tự kiểm chứng.
          </h2>
          <p style={{color: C.muted, fontSize: 21, marginTop: 16, lineHeight: 1.45}}>
            Còn nếu muốn nghe thật cách tôi chọn ngách phim kéo triệu view & bật kiếm tiền Facebook,
            <br />
            hẹn gặp nhau trong <strong style={{color: C.ink}}>Buổi Meet 50.000đ (chỉ bằng 1 cốc cà phê)</strong> cuối tuần này!
          </p>

          <div style={{display: 'inline-flex', gap: 18, marginTop: 30}}>
            <div
              style={{
                transform: `scale(${pulse})`,
                padding: '18px 34px',
                borderRadius: 14,
                background: C.accent,
                color: C.accentInk,
                fontSize: 21,
                fontWeight: 800,
                boxShadow: '0 18px 48px rgba(218,250,156,0.35)',
              }}
            >
              Nhập Gmail Tải Bản .EXE (0đ) ↑
            </div>
            <div
              style={{
                padding: '18px 28px',
                borderRadius: 14,
                background: C.glass,
                border: `1px solid ${C.border}`,
                color: C.ink,
                fontSize: 21,
                fontWeight: 700,
              }}
            >
              Vào Nhóm Meet Thực Chiến: 50.000đ
            </div>
          </div>
        </div>
      </AbsoluteFill>

      <SubtitlePill
        text="“Tải miễn phí bản .EXE phía trên — hoặc hẹn gặp bạn tại buổi Meet 50.000đ tối Chủ Nhật!”"
        accentWord="buổi Meet 50.000đ"
      />
    </AbsoluteFill>
  );
};

export const PromoVideo: React.FC = () => {
  return (
    <AbsoluteFill style={{backgroundColor: C.bg}}>
      <Audio src={staticFile('cinematic_master.mp3')} volume={1} />
      <Sequence from={0} durationInFrames={240}>
        <Act1FounderConfession />
      </Sequence>
      <Sequence from={240} durationInFrames={240}>
        <Act2SelfRescue />
      </Sequence>
      <Sequence from={480} durationInFrames={330}>
        <Act3FacebookPayoutAndViews />
      </Sequence>
      <Sequence from={810} durationInFrames={270}>
        <Act4PeerInviteCTA />
      </Sequence>
    </AbsoluteFill>
  );
};
