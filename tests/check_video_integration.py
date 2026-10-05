"""Simulate the video integration lifted from core_top.sv and the real filter."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOP = ROOT / "target/pocket/core_top.sv"


def between(source, start, end):
    return source[source.index(start):source.index(end, source.index(start))]


top = TOP.read_text()
source_block = between(top, "  // All styles share aligned RGB/sync/blanking", "  reg video_de_reg;")
pocket_gate = between(top, "  //create aditional switch to blank Pocket screen.", "//switch between Analogizer SNAC")
pocket_consumer = between(top, "  reg video_de_reg;", "  // Sound")
source_block = source_block.replace("  wire [23:0] video_rgb_analog = video_rgb_composite;\n", "")
source_block = source_block.replace("  reg analog_hblank = 1'b1;\n", "")
source_block = source_block.replace("  reg analog_vblank = 1'b1;\n", "")
source_block = source_block.replace("  reg analog_hsync = 1'b0;\n", "")
source_block = source_block.replace("  reg analog_vsync = 1'b0;\n", "")
pocket_gate = pocket_gate.replace("  wire [23:0] video_rgb_pocket;\n", "")
for expected in (
    "video_rgb_analog = video_rgb_composite",
    ".rgb_out(video_rgb_composite_raw)",
    ".hblank_out(analog_hblank_raw)",
    ".hsync_out(analog_hsync_raw)",
    ".vsync_out(analog_vsync_raw)",
    "wire de = analog_de",
    "video_rgb_reg <= video_rgb_pocket",
    "video_vs_reg <= ~vs_prev && analog_vsync",
):
    assert expected in top, f"missing actual source wiring: {expected}"

wrapper = f"""
module video_integration(
  input clk_video_5_37, input [3:0] composite_blend_mode,
  input h_blank, v_blank, video_hs_nes, video_vs_nes,
  input [23:0] video_rgb_nes,
  input pocket_blank_screen, analogizer_ena_s,
  input hide_overscan_with_region, square_pixels,
  output [23:0] video_rgb, output video_de, video_hs, video_vs,
  output [23:0] video_rgb_analog,
  output reg analog_hblank, analog_vblank, analog_hsync, analog_vsync
);
  wire [23:0] video_rgb_pocket;
  assign video_rgb_analog = video_rgb_composite;
  wire video_rgb_clock, video_rgb_clock_90;
  wire clk_video_5_37_90deg = clk_video_5_37;
  {pocket_gate}
  {source_block}
  {pocket_consumer}
endmodule
"""

tb = r"""
`timescale 1ns/1ps
module integration_tb;
  reg clk=0; always #5 clk=~clk;
  reg [3:0] mode=0; reg hb=1,vb=1,hs=0,vs=0;
  reg [23:0] rgb=0; reg pb=0,ae=0,hide=0,square=0;
  wire [23:0] pocket,analog_rgb;
  wire de,phs,pvs,ahb,avb,ahs,avs;
  video_integration dut(clk,mode,hb,vb,hs,vs,rgb,pb,ae,hide,square,
                        pocket,de,phs,pvs,analog_rgb,ahb,avb,ahs,avs);
  reg hb_q=1,vb_q=1,hs_q=0,vs_q=0;
  reg hb_qq=1,vb_qq=1,hs_qq=0,vs_qq=0;
  reg [23:0] rgb_q=0,rgb_qq=0;
  reg de_q=0;
  reg [23:0] analog_snapshot;
  reg [23:0] pocket_expected;
  reg pre_hs,pre_vs,want_phs,want_pvs,pre_de,want_metadata;
  reg model_hs_prev=0,model_vs_prev=0;
  reg model_de_prev=0;
  integer model_hs_delay=0,next_hs_delay;
  integer samples=0, metadata_slots=0, mode_seen=0;
  reg [3:0] analog_meta_snapshot;
  reg [26:0] pocket_snapshot;
  initial begin
    repeat(8) @(negedge clk);
    for (integer i=0;i<2700;i=i+1) begin
      // Let the synchronized mode settle, then exercise every setting over
      // changing pixels, blanking, and sync transitions.
      mode=(i/300)%9;
      hb=(i%96)>=72; vb=(i%521)<20;
      hs=(i%96)>=80 && (i%96)<87; vs=(i%521)<4;
      rgb={8'(i*37),8'(i*71),8'(i*113)};
      pb=(i%41)==0; ae=(i%43)==0; hide=i[0]; square=i[1];
      pocket_expected=(pb && !ae) ? 24'h0 : analog_rgb;
      pre_hs=ahs; pre_vs=avs;
      pre_de=!(ahb || avb);
      want_metadata=model_de_prev && !pre_de;
      want_phs=(model_hs_delay==1);
      want_pvs=pre_vs && !model_vs_prev;
      next_hs_delay=(model_hs_delay>0) ? model_hs_delay-1 : 0;
      if (!model_hs_prev && pre_hs) next_hs_delay=7;
      @(posedge clk); #1;
      if ({ahb,avb,ahs,avs} !== {hb_qq,vb_qq,hs_qq,vs_qq})
        $fatal(1,"filter metadata/sync is not aligned at sample %0d",i);
      if (mode==0 && (i%300)>8 && analog_rgb !== rgb_qq)
        $fatal(1,"Off RGB differs from two-edge-aligned upstream RGB at sample %0d: %h != %h",i,analog_rgb,rgb_qq);
      if (de !== de_q) $fatal(1,"Pocket DE lost delayed blanking alignment at %0d",i);
      if (i>100 && {phs,pvs} !== {want_phs,want_pvs})
        $fatal(1,"Pocket H/V sync pulse alignment mismatch at %0d",i);
      if (want_metadata) begin
        if (pocket !== {9'b0,hide,square,10'b0,3'b0})
          $fatal(1,"Pocket metadata slot mismatch at %0d: %h",i,pocket);
        metadata_slots=metadata_slots+1;
      end
      if (de) begin
        if (pocket !== pocket_expected)
          $fatal(1,"Pocket RGB or blank-screen gate mismatch at %0d",i);
      end
      mode_seen[mode]=1'b1;
      mode_seen[dut.composite_blend_video]=1'b1;
      hb_qq=hb_q; vb_qq=vb_q; hs_qq=hs_q; vs_qq=vs_q; rgb_qq=rgb_q;
      hb_q=hb; vb_q=vb; hs_q=hs; vs_q=vs; rgb_q=rgb;
      de_q=!(ahb || avb);
      model_hs_delay=next_hs_delay;
      model_hs_prev=pre_hs; model_vs_prev=pre_vs;
      model_de_prev=pre_de;
      analog_snapshot=analog_rgb;
      analog_meta_snapshot={ahb,avb,ahs,avs};
      pocket_snapshot={pocket,de,phs,pvs};
      @(negedge clk);
      // Glitch all asynchronous video inputs while the pixel clock is low.
      // Registered Analogizer output must hold until the next rising edge.
      rgb=~rgb; hb=~hb; vb=~vb; hs=~hs; vs=~vs;
      #1;
      if (analog_rgb !== analog_snapshot || {ahb,avb,ahs,avs} !== analog_meta_snapshot)
        $fatal(1,"Analogizer RGB or sync/blanking changed between pixel edges at sample %0d",i);
      if ({pocket,de,phs,pvs} !== pocket_snapshot)
        $fatal(1,"Pocket RGB, DE, or sync changed between pixel edges at sample %0d",i);
      samples=samples+1;
    end
    if (mode_seen !== 9'b111111111) $fatal(1,"not all nine filter modes were exercised: %b",mode_seen);
    $display("PASS: %0d sampled cycles across sequential mode changes 0-8; %0d Pocket metadata slots checked",samples,metadata_slots);
    $finish;
  end
endmodule
"""

with tempfile.TemporaryDirectory() as temp:
    temp = Path(temp)
    harness = temp / "integration.sv"
    image = temp / "integration"
    harness.write_text(wrapper + "\n" + tb)
    subprocess.run(["iverilog", "-g2012", "-s", "integration_tb", "-o", str(image),
                    str(harness), str(ROOT / "platform/pocket/common.v"),
                    str(ROOT / "target/pocket/composite_blend.sv")], check=True)
    subprocess.run(["vvp", str(image)], check=True)
