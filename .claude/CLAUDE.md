# B1Web – mô hình 3D nhà B1 (ĐH Bách khoa Hà Nội)

## Môi trường (đã xác minh, không cần dò lại)
- OS: Windows 11, shell chính PowerShell 5.1 (có Git Bash). Không phải git repo.
- Blender 5.2: `D:\Blender Foundation\Blender 5.2\blender.exe` (có trong PATH là `blender`).
- Không có Blender MCP trong session – chạy headless bằng CLI.

## Chạy dựng mô hình
```
"D:\Blender Foundation\Blender 5.2\blender.exe" -b "D:\Project III\B1Web\blender\B1.blend" -P "D:\Project III\B1Web\blender\build_b1.py" -- "D:\Project III\B1Web\map (3).osm"
```
- Script chỉ dựng lại collection `B1_OSM`; chạy lại nhiều lần không nhân đôi object (đã kiểm tra).
- Dựng + render: `blender -b B1.blend -P render_views.py -- "D:\Project III\B1Web\map (3).osm" Cam_Ref Cam_Lobby Cam_Porch Cam_Aerial` (chạy trong `blender/`, mỗi lần ~5 s, EEVEE) → ảnh vào `blender/renders/`. Script này không lưu .blend.
- Camera: `Cam_Ref` (gần góc chụp ref.jpg), `Cam_Aerial`, `Cam_Lobby` (nhìn thẳng vành sảnh), `Cam_Porch` (dưới mái đón xe).
- Bản cũ trước khi tách module: `blender/_backup/build_b1_v1.py`, `blender/_backup/B1_v1.blend`.

## Cấu trúc code
- `blender/build_b1.py` – entry, nạp lại package `blender/b1/` mỗi lần chạy.
- `blender/b1/`: `config` (hằng số, cờ `BUILD_CONTEXT`), `osm`, `geom`, `meshkit` (MB + primitive), `materials`, `wings` (mỗi building:part OSM = 1 object), `lobby` (sảnh chính), `tower` (tháp thang tròn), `rooftop`, `context`, `scene`, `main`.
- Dữ liệu: `map (3).osm` – B1 là way `184021007`, phần sảnh cong là building:part `1207082389`.

## Ảnh tham chiếu (thư mục gốc)
- `ref.jpg` – toàn cảnh mặt trước (vành tròn sảnh, tháp thang tròn, chữ B1).
- `116c18eb-…jpg` – vành tròn sảnh + mái đón xe cận cảnh.
- `047b7416-…jpg` – mái đón xe nhìn nghiêng, cột inox, tường kem tầng 1.
- `84666966-…jpg` – dưới mái đón xe: trần xám đậm, ô trần lõm, cửa kính khung đen, tường kem.
- `sảnh.png` – sketch của user: TRÁI = mặt đứng mái đón xe (viền vát) + 2 cột tròn + thềm 2 bậc (+ bồn cây loe 2 bên – chưa làm); PHẢI = khung cửa kính sảnh chính, 5 ô × 3 hàng, hàng dưới có 2 bộ cửa đôi.

## Quyết định đã chốt với user
- Tòa nhà phải tách thành nhiều module con: cả file Python lẫn object/collection trong Blender ("nhiều mảnh ghép").
- **Chỉ tầng 1 của sảnh chính** tường vàng kem; vành tròn tầng 2 tường trắng; các cánh nhà khác trắng.
- Mái đón xe: tấm thẳng xám đậm, viền vát, 2 cột inox tròn, thềm 2 bậc đá.
- Hướng: trục y của model = hướng bắc. Ảnh ref chụp từ bãi xe phía bắc/tây bắc nên **bên trái ảnh = phía đông**. Vành sảnh: P[0] ở đầu tây, P[NS] ở đầu đông.
- Vành sảnh dựng theo cung tròn qua 3 điểm OSM (R ≈ 20.3 m, dài cung 25.3 m). Vị trí cửa sổ vành nằm ở `RING_WINDOWS` trong `b1/lobby.py`, tính theo tỉ lệ từ đầu tây: ô hẹp 4 cột ở phía tây, ô rộng 7 cột, khe cửa hẹp sát đầu đông.
- Cửa chính và mái đón xe **lệch về phía đông** (`ENTRY_F = 0.56`), không nằm giữa vành.
- Trước mắt chỉ làm tòa nhà: không vẽ cây/bồn cây; context (đường, xe, nhà xung quanh) tắt mặc định (`BUILD_CONTEXT=False`).

## Cập nhật (lượt 2)
- Bậc thềm sảnh: 5 bậc (`N_STEPS` trong `b1/lobby.py`).
- Cụm cửa sổ (sketch user, `sảnh.png`-style "mỗi cụm cửa sổ"): mỗi nhịp = 3 cửa sổ giống hệt nhau (dải trên + 2 ô dưới) ngăn bởi 2 panel đứng hẹp viền dày; tất cả dùng 1 material `B1_GlassCluster` (không random). Hàm `cluster_window` trong `b1/wings.py`.
- Vùng áp dụng hiện tại = các mặt đứng nhịp (không phải gable) có pháp tuyến hướng về phía camera ref (`CLUSTER_FACING`, `CLUSTER_MIN_DOT` trong `b1/wings.py`): cánh đông bậc thang (bên trái ảnh ref) và mặt chính cánh tây 10F/8F/5F (bên phải). Các mặt khác (gable, mặt sau) vẫn dùng `strip_window` ngẫu nhiên – user sẽ chỉ vùng tiếp theo sau.
- Kính tầng 1 hai bên cửa chính (sketch lượt 3): mỗi "unit" = tường kem | dải kính trên (5 ô) | dải tường kem ngang | dải kính dưới (5 ô) | tường kem; hàm `shop_unit` trong `b1/lobby.py` (`UNIT_W`, `BANK_Z`). Số unit mỗi bên tự chia theo chiều dài cung (tây 2, đông 1).
- Cụm cửa sổ (chốt lượt 5): 3 ô cửa (mỗi ô có nẹp giữa), giữa 2 ô liền kề là 1 panel chữ nhật hẹp (`CLUSTER_PANEL_W = 0.5`) cao suốt chiều cao cửa, **viền panel mỏng bằng viền cửa sổ** (không dày hơn), đường ngang (transom) chạy xuyên qua cả panel. User muốn làm đúng sát hình họ gửi, đừng tự thêm chi tiết.
