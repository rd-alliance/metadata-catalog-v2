/* For fields repeated as list items */

function autoduplicate() {
  var new_li = $( this ).clone( true );
  $( new_li ).find( "label" ).attr( "for", function(index, value) {
    return value.replace(/-(\d+)(-\w+)?$/, function(str, p1, p2, offset, s) {
      if ( p2 ) {
      return '-' + (Number(p1) + 1) + p2;
      }
      return '-' + (Number(p1) + 1);
    });
  });
  $( new_li ).find( ":input" ).attr( "id", function(index, value) {
    return value.replace(/-(\d+)(-\w+)?$/, function(str, p1, p2, offset, s) {
      if ( p2 ) {
      return '-' + (Number(p1) + 1) + p2;
      }
      return '-' + (Number(p1) + 1);
    });
  });
  $( new_li ).find( ":input" ).attr( "name", function(index, value) {
    return value.replace(/-(\d+)(-\w+)?$/, function(str, p1, p2, offset, s) {
      if ( p2 ) {
      return '-' + (Number(p1) + 1) + p2;
      }
      return '-' + (Number(p1) + 1);
    });
  });
  $( new_li ).find( ":input" ).val(function() {return this.defaultValue});
  $( new_li ).one( "change", autoduplicate );
  $( this ).after( new_li );
}

$( ".form-list > li:last-child" )
  .one( "change", autoduplicate );

$( "div > span:last-child").has( "input[list='keyword-list']" )
  .one( "change", autoduplicate );

/* Cleaning help text */

$( ".form-group" ).find( ".form-text" ).hide();

$( ":input" ).focus(function() {
  $( this ).closest( ".form-group" ).find( ".form-text" )
  .filter( ":hidden" ).show(400);
});

$( ".form-group" ).focusout(function (event) {
  if ( $( this ).has( event.relatedTarget ).length == 0 ) {
    $( this ).find( ".form-text" ).hide(400);
  }
});

/*
Accessibility for alerts

1. When the announcement bar is dismissed, focus on <main>.
2. When an alert in the #alerts <div> is dismissed, pass
   focus back up to the #alerts <div>.
*/
$( "aside.alert" ).on("closed.bs.alert", function(){
  $( "main" ).first().attr("tabindex", -1).focus();
});
$( "#alerts" ).children().on("closed.bs.alert", function(){
  $( "#alerts" ).attr("tabindex", -1).focus();
});
