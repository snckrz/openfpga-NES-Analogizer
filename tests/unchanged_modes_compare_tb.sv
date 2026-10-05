`timescale 1ns/1ps
// Compare actual candidate RTL against the frozen test2 RTL. RGB is required
// to stay bit-exact for modes 0,1,2,3,5,6; metadata is compared every cycle.
module unchanged_modes_compare_tb;
  reg clk=0;
  reg [3:0] mode=0;
  reg hb=1,vb=1,hs=0,vs=0,dotc=0,intl=0;
  reg [23:0] rgb=0;
  wire [23:0] new_rgb,old_rgb;
  wire new_hb,new_vb,new_hs,new_vs,new_dot;
  wire old_hb,old_vb,old_hs,old_vs,old_dot;
  integer checks=0;
  integer coverage[0:8];
  integer seed=32'h534e4553;
  integer line_no=0, x, width, m, k;

  composite_blend candidate(
    .clk(clk),.mode(mode),.hblank_in(hb),.vblank_in(vb),.hsync_in(hs),.vsync_in(vs),
    .dotclk_in(dotc),.interlace_in(intl),.rgb_in(rgb),.rgb_out(new_rgb),
    .hblank_out(new_hb),.vblank_out(new_vb),.hsync_out(new_hs),.vsync_out(new_vs),
    .dotclk_out(new_dot));
  composite_blend_baseline baseline(
    .clk(clk),.mode(mode),.hblank_in(hb),.vblank_in(vb),.hsync_in(hs),.vsync_in(vs),
    .dotclk_in(dotc),.interlace_in(intl),.rgb_in(rgb),.rgb_out(old_rgb),
    .hblank_out(old_hb),.vblank_out(old_vb),.hsync_out(old_hs),.vsync_out(old_vs),
    .dotclk_out(old_dot));
  always #5 clk=~clk;

  task automatic tick(input [3:0] m,input bit hbi,vbi,hsi,vsi,di,
                      input bit inter,input [23:0] color);
    begin
      @(negedge clk);
      mode=m; hb=hbi; vb=vbi; hs=hsi; vs=vsi; dotc=di; intl=inter; rgb=color;
      @(posedge clk); #1;
      if ({new_hb,new_vb,new_hs,new_vs,new_dot} !==
          {old_hb,old_vb,old_hs,old_vs,old_dot})
        $fatal(1,"candidate/baseline metadata mismatch cycle=%0d mode=%0d",checks,m);
      if (m==0 || m==1 || m==2 || m==3 || m==5 || m==6) begin
        if (new_rgb !== old_rgb)
          $fatal(1,"unchanged mode RGB mismatch cycle=%0d mode=%0d input=%06h old=%06h new=%06h",checks,m,color,old_rgb,new_rgb);
        coverage[m]=coverage[m]+1;
      end
      checks=checks+1;
    end
  endtask

  initial begin
    for(k=0;k<9;k=k+1) coverage[k]=0;
    tick(0,1,1,0,0,0,0,0);
    tick(0,1,1,0,1,0,0,0);
    tick(0,1,0,0,0,0,0,0);
    // Repeated rows exercise PAL line RAM alignment, plus mode transitions
    // through every edited and unedited selection. Widths include 1, short,
    // normal and the 512/513 sample PAL memory boundary.
    for(line_no=0;line_no<45;line_no=line_no+1) begin
      m=line_no%9;
      case(line_no%6)
        0: width=1;
        1: width=3;
        2: width=24;
        3: width=257;
        4: width=512;
        default: width=513;
      endcase
      tick(m[3:0],1,0,0,vs,0,(line_no%4)==3,24'h000000);
      for(x=0;x<width;x=x+1) begin
        tick(m[3:0],0,0,x[0],vs,x[0],(line_no%4)==3,$random(seed));
      end
      tick(m[3:0],1,0,1,vs,1,(line_no%4)==3,$random(seed));
      tick(m[3:0],1,0,0,vs,0,(line_no%4)==3,24'hffffff);
      tick(m[3:0],1,0,0,vs,1,(line_no%4)==3,24'h000000);
      if(line_no%9==8) begin
        tick(m[3:0],1,1,0,0,0,0,0);
        tick(m[3:0],1,1,0,1,0,0,0);
        tick(m[3:0],1,0,0,0,0,0,0);
      end
    end
    for(k=0;k<9;k=k+1)
      if((k==0 || k==1 || k==2 || k==3 || k==5 || k==6) && coverage[k]==0)
        $fatal(1,"unchanged mode %0d was not compared",k);
    $display("PASS: %0d samples; unchanged mode coverage 0=%0d 1=%0d 2=%0d 3=%0d 5=%0d 6=%0d; metadata compared every cycle",checks,coverage[0],coverage[1],coverage[2],coverage[3],coverage[5],coverage[6]);
    $finish;
  end
endmodule
