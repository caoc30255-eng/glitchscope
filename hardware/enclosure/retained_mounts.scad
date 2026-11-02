// Included by case_v16.scad. Dimensions are prototype clearances, not fit approval.
module tray(){difference(){union(){
 ring(W,D,3,10);
 for(p=CORNERS)translate([p[0],p[1],0])cylinder(d=11,h=3);
 }for(p=CORNERS)translate([p[0],p[1],-E])cylinder(d=3.4,h=4);
 // Movable beam ends: independent Y adjustment, beyond the PCB envelope.
 for(x=[5,W-5])translate([0,0,-E])slot([x,20,0],[x,120,0],3.4,4);

 }}
module beam(){difference(){cube([W,10,3]);
 for(x=[5,W-5])translate([x,5,-E])cylinder(d=3.4,h=4);
 translate([0,0,-E])slot([20,5,0],[160,5,0],3.4,4);
 }}
module beams(){for(y=[29,111])translate([0,y-5,55])beam();}
// L brackets support flat panels. Upper brackets have a roof screw boss.
module corner_clip(roof=false){difference(){union(){
 cube([2.4,12,10]);cube([12,2.4,10]);
 if(roof){translate([0,0,8])cube([12,12,2]);translate([3,3,2])cube([6,6,8]);}
 }translate([-E,6,5])rotate([0,90,0])cylinder(d=2,h=3);
 translate([6,-E,5])rotate([-90,0,0])cylinder(d=2,h=3);
 if(roof)translate([6,6,1.9])cylinder(d=2,h=9);
 }}
module place_corner(i,z){
 if(i==0)translate([-1.8,-4,z])children();
 if(i==1)translate([W+1.8,-4,z])mirror([1,0,0])children();
 if(i==2)translate([-1.8,174,z])mirror([0,1,0])children();
 if(i==3)translate([W+1.8,174,z])mirror([1,0,0])mirror([0,1,0])children();
}
module clips(){for(i=[0:3]){place_corner(i,12)corner_clip();place_corner(i,98)corner_clip(true);}}

module side_panel(right=false){difference(){
 translate([right?W+1.8:-3,-4+FIT,0])cube([P,178-2*FIT,108-FIT]);
 for(y=[2,168],z=[17,103])translate([right?W+1:-4,y,z])rotate([0,90,0])cylinder(d=2.8,h=4);
 for(y=[35,105])translate([right?W+1:-4,y,4])rotate([0,90,0])cylinder(d=2.8,h=4);
 if(right)translate([W+1,50,12])cube([4,67,20]);
 else translate([-4,82,12])cube([4,18,8]);
 }}
module face_panel(back=false){difference(){
 translate([-3,back?174:-5.2,0])cube([W+6,P,108-FIT]);
 for(x=[4.2,175.8],z=[17,103])translate([x,back?173:-6,z])rotate([-90,0,0])cylinder(d=2.8,h=4);
 translate([16,back?173:-6,12])cube([W-32,4,30]);
 translate([25,back?173:-6,66])cube([136,4,30]);
 if(back)for(x=[45:12:125])translate([x,173,47])cube([8,4,4]);
 }}
module roof(){difference(){union(){
 translate([-3,-5.2,108])cube([186,180.4,P]);
 for(y=[35,85,135])translate([20,y,106])cube([140,2,2.05]);
 }for(x=[4.2,175.8],y=[2,168])translate([x,y,107])cylinder(d=2.8,h=4);
 for(y=[40:8:110])translate([65,y,105])cube([50,4,6]);
 }}
module coupon(){difference(){cube([74,36,3]);
 for(i=[0:4])translate([9+i*13,10,-E])cylinder(d=2.6+i*.2,h=4);
 for(i=[0:3])translate([9+i*15,25,-E])cylinder(d=1.8+i*.2,h=4);
 }translate([68,20,3])cube([1.2,12,8]);}

// 7020: support acrylic edges at Z7, not the PCB or the speaker.
module base(){difference(){union(){
 ring(W,D,3,6);
 for(y=[0,131])translate([0,y,0])cube([W,9,3]);
 for(x=[5.5,171.5])translate([x,60,0])cube([3,20,10]);
 for(p=CORNERS)translate([p[0],p[1],0])cylinder(d=11,h=3);
 for(y=[9,124])translate([30,y,3-E])cube([120,7,4+E]);
 for(x=[9,164])translate([x,30,3-E])cube([7,80,4+E]);
 for(x=[41,131],y=[0,123])translate([x,y,0])cube([8,17,3]);
 for(x=[0,163],y=[46,86])translate([x,y,0])cube([17,8,3]);
 for(x=[-1.8,W-6],y=[35,105])translate([x,y-4,0])cube([7.8,8,8]);
 }for(p=CORNERS)translate([p[0],p[1],-E])cylinder(d=3.4,h=4);
 for(y=[5,135])translate([0,0,-E])slot([30,y,0],[150,y,0],3.4,4);
 for(x=[-3,W-7],y=[35,105])translate([x,y,4])rotate([0,90,0])cylinder(d=2.4,h=11);
 }}
module edge_clamp(){difference(){union(){cube([14,8,8.7]);translate([0,7,6.3])cube([14,5,2.4]);}
 translate([7,4,-E])cylinder(d=3.4,h=10);
 }}
module clamps(){for(x=[45,135]){
 translate([x-7,1,3])edge_clamp();
 translate([x-7,139,3])mirror([0,1,0])edge_clamp();
 }}
// Full retained acrylic plates. Exact cuts and hole locations remain provisional.
module acrylic_lower(edge=false){difference(){
 translate([10,10,7])cube([160,120,2]);
 for(p=HOLES)translate([10+p[0],10+p[1],6.9])cylinder(d=3.4,h=2.2);
 if(edge)translate([12,12,6.9])cube([156,116,2.2]);
 }}
module acrylic_upper(edge=false){difference(){
 translate([25.5,25.5,83.8])cube([129,89,2.8]);
 // Illustrative service notches from photos, not fabrication coordinates.
 translate([24,38,83])cube([8,61,5]);
 translate([52,24,83])cube([87,8,5]);
 translate([124,104,83])cube([32,12,5]);
 for(p=AX)translate([25+p[0],25+p[1],83])cylinder(d=3.4,h=5);
 if(edge)translate([27.5,27.5,83])cube([125,85,5]);
 }}
module original_standoffs(){for(p=AX)translate([25+p[0],25+p[1],69.6])difference(){
 cylinder(d=5.5,h=14.2,$fn=6);translate([0,0,-E])cylinder(d=3,h=15);
 }}
module new_isolators(){for(p=AX)translate([25+p[0],25+p[1],58])difference(){
 cylinder(d=5.5,h=10,$fn=6);translate([0,0,-E])cylinder(d=3,h=11);
 }}
module top_screws(){for(p=AX)translate([25+p[0],25+p[1],86.6])cylinder(d=5.5,h=2);}
module lower_screws(){for(p=HOLES)translate([10+p[0],10+p[1],5])cylinder(d=5.5,h=2);}
module beam_screws(){for(p=AX){
 translate([25+p[0],25+p[1],53])cylinder(d=5.5,h=2);
 // Thread engagement and length deliberately not represented as verified.
 translate([25+p[0],25+p[1],55])cylinder(d=2.8,h=6);
 }}
module lower_original_posts(){for(p=HOLES)translate([10+p[0],10+p[1],9])difference(){cylinder(d=5.5,h=6,$fn=6);translate([0,0,-E])cylinder(d=3,h=7);}}
module speaker(){translate([48,53,11])difference(){cylinder(d=29,h=4);translate([0,0,-E])cylinder(d=21,h=1);}}
module sd_upper(){difference(){translate([77,24,65.8])cube([15,15,2.2]);translate([78,23.9,66.2])cube([13,10,1.2]);}}

if(PART=="base")base();
if(PART=="feet")feet();
if(PART=="columns")columns();
if(PART=="upper")translate([0,0,52])tray();
if(PART=="beams")beams();
if(PART=="clamps")clamps();
if(PART=="clips")clips();
if(PART=="side_left")side_panel();
if(PART=="side_right")side_panel(true);
if(PART=="front")face_panel();
if(PART=="back")face_panel(true);
if(PART=="roof")roof();
if(PART=="pcb7020")board(0);
if(PART=="pcb7010")board(1);
if(PART=="lettering")label();
if(PART=="acrylic7020")acrylic_lower();
if(PART=="acrylic7010")acrylic_upper();
if(PART=="acrylic_edge7020")acrylic_lower(true);
if(PART=="acrylic_edge7010")acrylic_upper(true);
if(PART=="original_posts7020")lower_original_posts();
if(PART=="original_posts7010")original_standoffs();
if(PART=="new_isolators7010")new_isolators();
if(PART=="top_screws7010")top_screws();
if(PART=="bottom_screws7020")lower_screws();
if(PART=="beam_screws7010")beam_screws();
if(PART=="speaker7020")speaker();
if(PART=="sd7010")sd_upper();
for(board=["7020","7010"]){
 if(PART==str("metal",board))ports(board,"metal");
 if(PART==str("plastic",board)){ports(board,"plastic");headers(board);}
 if(PART==str("accent",board))ports(board,"accent");
 if(PART==str("gold",board)){ports(board,"gold");headers(board,true);}
}
if(PART=="sd7020")sd_slot();
if(PART=="assembly"){
 color("SlateGray"){base();feet();columns();translate([0,0,52])tray();beams();clamps();clips();}
 color("Black"){side_panel();side_panel(true);face_panel();face_panel(true);roof();speaker();}
 color("RoyalBlue")board(0);color("FireBrick")board(1);
 color([.7,.85,.95,.18]){acrylic_lower();acrylic_upper();}
 color("Goldenrod"){original_standoffs();new_isolators();lower_original_posts();}
 color("Silver"){top_screws();lower_screws();beam_screws();}
}


// Printer-only exports: retained acrylic, PCBs and metal fittings are excluded.
if(PART=="print_base")base();
if(PART=="print_column")column();
if(PART=="print_upper")tray();
if(PART=="print_beam")beam();
if(PART=="print_foot")foot();
if(PART=="print_edge_clamp")edge_clamp();
if(PART=="print_corner_clip")corner_clip();
if(PART=="print_roof_clip")translate([0,12,10])rotate([180,0,0])corner_clip(true);
if(PART=="print_side_left")multmatrix([[0,1,0,3.75],[0,0,1,0],[1,0,0,3],[0,0,0,1]])side_panel();
if(PART=="print_side_right")multmatrix([[0,1,0,3.75],[0,0,1,0],[-1,0,0,183],[0,0,0,1]])side_panel(true);
if(PART=="print_front")multmatrix([[1,0,0,3],[0,0,1,0],[0,1,0,5.2],[0,0,0,1]])face_panel();
if(PART=="print_back")multmatrix([[1,0,0,3],[0,0,1,0],[0,-1,0,175.2],[0,0,0,1]])face_panel(true);
if(PART=="print_roof")translate([3,175.2,109.2])rotate([180,0,0])roof();
if(PART=="print_coupon")coupon();
