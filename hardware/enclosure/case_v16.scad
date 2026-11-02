// v16 retained-acrylic PETG first-fit design, 1.2mm flat detachable skins. No PP.
// No fan installed; passive openings retained.
// Stacked prototype: 7020 lower, AX7010 upper, both components upward.
// Four independent chassis columns carry the upper tray; retained acrylic is not printed.
PART="assembly"; $fn=32; E=.05;
W=180; D=140; DEPTH=170; H=108; P=1.2; FIT=.25;
Z_LOW=15; Z_TRAY=52; Z_HIGH=68;
HOLES=[[4.2,4.7],[156.2,4.2],[3.9,116.1],[156.3,116.0]];
AX=[[4,4],[126,4],[4,86],[126,86]]; // Placeholder, not measured!
CORNERS=[[5,5],[175,5],[5,135],[175,135]];
module ring(w,d,t,b){difference(){cube([w,d,t]);translate([b,b,-E])cube([w-2*b,d-2*b,t+2*E]);}}
module slot(a,b,d,h){hull(){translate(a)cylinder(d=d,h=h);translate(b)cylinder(d=d,h=h);}}
module column(){difference(){cylinder(d=9,h=49);translate([0,0,-E])cylinder(d=3.4,h=50);}}
module columns(){for(p=CORNERS)translate([p[0],p[1],3])column();}

module spacer(){difference(){cylinder(d=8,h=3);translate([0,0,-E])cylinder(d=3.4,h=4);}}

module foot(){difference(){cylinder(d=11,h=6);translate([0,0,-E])cylinder(d=3.4,h=7);translate([0,0,-E])cylinder(d=6,h=3);}}
module feet(){for(p=CORNERS)translate([p[0],p[1],-6])foot();}
// Two light end hoops support the PP roof without loading the PCB/components.




module board(i){translate([i==0?10:25,i==0?10:25,i==0?Z_LOW:Z_HIGH]){
 cube([i==0?160:130,i==0?120:90,1.6]);
 translate([i==0?55:43,i==0?40:28,1.6])cube([44,38,i==0?14:3]);
 }}
module label(){translate([W+3.12,28,74])rotate([90,0,90])linear_extrude(.1)text("GLITCHSCOPE",size=6,font="Liberation Sans:style=Bold");}
PORTS=[["7020", "CAN terminal", "terminal", 19, 118, 16.6, 11, 12, 10, "back"], ["7020", "RS485 terminal", "terminal", 32, 118, 16.6, 11, 12, 10, "back"], ["7020", "DB9 COM", "db9", 45, 117, 16.6, 30, 14, 12.5, "back"], ["7020", "USB_HOST1", "usb", 78, 114, 16.6, 8, 17, 14, "back"], ["7020", "USB_HOST2", "usb", 87, 114, 16.6, 8, 17, 14, "back"], ["7020", "USB_HOST3", "usb", 96, 114, 16.6, 8, 17, 14, "back"], ["7020", "USB_HOST4", "usb", 105, 114, 16.6, 8, 17, 14, "back"], ["7020", "GE_PL RJ45", "rj45", 115, 109, 16.6, 16, 22, 13.6, "back"], ["7020", "GE_PS RJ45", "rj45", 135, 109, 16.6, 16, 22, 13.6, "back"], ["7020", "DC_IN", "dc", 153, 117, 16.6, 10, 14, 11, "back"], ["7020", "HDMI", "hdmi", 28, 9, 16.6, 15, 12, 6, "front"], ["7020", "USB_UART Type-C", "typec", 48, 9, 16.6, 9, 8, 3.5, "front"], ["7020", "USB_SLAVE Type-C", "typec", 61, 9, 16.6, 9, 8, 3.5, "front"], ["7020", "LINE_IN", "audio", 157, 59, 16.6, 14, 12, 10, "right"], ["7020", "PHONE", "audio", 157, 76, 16.6, 14, 12, 10, "right"], ["7020", "AV", "audio", 157, 93, 16.6, 14, 12, 10, "right"], ["7010", "RJ45", "rj45", 30, 94, 69.6, 16, 22, 13.6, "back"], ["7010", "USB_UART mini", "mini", 56, 106, 69.6, 8, 10, 4, "back"], ["7010", "USB_SLAVE mini", "mini", 68, 106, 69.6, 8, 10, 4, "back"], ["7010", "USB_HOST", "usb", 86, 100, 69.6, 15, 16, 7, "back"], ["7010", "DC_IN", "dc", 133, 102, 69.6, 10, 14, 11, "back"], ["7010", "HDMI", "hdmi", 128, 24, 69.6, 15, 12, 6, "front"], ["7010", "USB_JTAG", "mini", 146, 24, 69.6, 8, 10, 4, "front"]];

module socket_hole(w,d,h,face){
 if(face=="back")translate([1,d-4,1])cube([w-2,4.1,h-2]);
 else translate([1,-.1,1])cube([w-2,4.1,h-2]);
}
module ports(board,group){for(p=PORTS)if(p[0]==board){
 typ=p[2];x=p[3];y=p[4];z=p[5];w=p[6];d=p[7];h=p[8];face=p[9];
 translate([x,y,z]){
 if(group=="metal"){
  if(typ!="dc"&&typ!="terminal"&&typ!="audio")difference(){cube([w,d,h]);socket_hole(w,d,h,face);}
  if(typ=="terminal")for(a=[w*.28,w*.72])translate([a,d*.45,h-.1])cylinder(d=2.8,h=.4);
  if(typ=="dc")translate([w/2,face=="back"?d-3:0,h/2])rotate([-90,0,0])cylinder(d=1.5,h=3);
 }
 if(group=="plastic"){
  if(typ=="dc")difference(){cube([w,d,h]);translate([w/2,face=="back"?d-4:-.1,h/2])rotate([-90,0,0])cylinder(d=6.4,h=4.2);}
  else if(typ=="audio")difference(){cube([w,d,h]);translate([w-4,d/2,h/2])rotate([0,90,0])cylinder(d=6,h=4.2);}
  else if(typ!="terminal")translate([1.1,face=="back"?d-4.1:3.1,1.1])cube([w-2.2,.8,h-2.2]);
 }
 if(group=="accent"){
  if(typ=="terminal")cube([w,d,h]);
  if(typ=="usb")translate([w*.35,face=="back"?d-3:0,h*.3])cube([w*.3,3,h*.4]);
 }
 if(group=="gold"&&typ=="rj45")for(a=[0:7])translate([2.5+a*1.5,face=="back"?d-.8:.2,1.2])cube([.5,.6,2.5]);
 }
}}
module headers(board,gold=false){
 z=board=="7020"?16.6:69.6;
 if(board=="7020"){
  if(!gold){translate([11,23,z])cube([5,50,2.5]);translate([157,25,z])cube([6,20,2.5]);}
  else{for(y=[25:2.54:70],x=[12,14.54])translate([x,y,z+2.5])cube([.6,.6,3]);}
 }else{
  if(!gold){for(x=[26,148])translate([x,36,z])cube([5,54,2.5]);}
  else for(x=[27,29.54,149,151.54],y=[38:2.54:88])translate([x,y,z+2.5])cube([.6,.6,3]);
 }
}
module sd_slot(){difference(){translate([9,84,16.6])cube([15,15,2]);translate([8.9,85,17])cube([10,13,1.2]);}}

include <retained_mounts.scad>;
